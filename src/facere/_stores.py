"""Stores as a batch of a build meets them: what each virtual output holds, and writing what recipes set, calling one store's methods at a time. Also the signatures of virtual sources."""

import os
import threading
import typing
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple

from facere._api import FileStore, Store
from facere._cache import HashCache, Look
from facere._collect import DeclaredStore, SourceEntry, VirtualEntry
from facere._hash import UnhashableValueError, calc_value_digest
from facere._state import StoreRecord

# The stamp of a FileStore whose file is missing, which holds no virtual outputs.
_ABSENT_FILE = "-"


def _as_store(store: DeclaredStore) -> Store[object, object]:
    """Return the value of a store other than a FileStore, which collection found by its methods' names."""
    return typing.cast("Store[object, object]", store.value)


class StoreError(Exception):
    """A store's `method` failed, for `reason`, raising `error` where it raised."""

    def __init__(
        self,
        store: DeclaredStore,
        method: str,
        reason: str,
        error: BaseException | None = None,
    ) -> None:
        super().__init__(f"store {store.name}: {method} {reason}")
        self.store = store
        self.method = method
        self.reason = reason
        self.error = error


class SignatureError(Exception):
    """A virtual source's signature function failed, for `reason`, raising `error` where it raised."""

    def __init__(self, reason: str, error: BaseException | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.error = error


def fetch_signature_digest(source: SourceEntry) -> str:
    """Return the digest of what the signature function of the virtual source `source` returns for its key. Raises SignatureError."""
    try:
        signature = source.fingerprint(source.key)
    except Exception as error:  # noqa: BLE001 - a signature function is the project's own
        raise SignatureError(f"raised {type(error).__name__}", error) from error
    try:
        return calc_value_digest(signature)
    except UnhashableValueError as error:
        raise SignatureError(
            f"returned a value of type {error.type_name}, which Facere can't hash, since {error.reason}"
        ) from None


class Change(NamedTuple):
    """A virtual output a finished recipe set: its engine key, the value, and the value's digest."""

    key: str
    value: object
    digest: str


class StoreSession:
    """One store as one batch sees it, calling the store's methods one at a time under its lock.

    `entries` holds the store's virtual outputs by engine key, in definition order, and `needed` the engine keys the batch's rules declare, which a read asks for. `recorded` is what the state held of the store.
    """

    def __init__(
        self,
        store: DeclaredStore,
        entries: dict[str, VirtualEntry],
        recorded: StoreRecord | None,
        cache: HashCache,
        calling_cb: Callable[[bool], None],
    ) -> None:
        self._store = store
        self._entries = entries
        self._recorded = recorded
        self._cache = cache
        self._calling_cb = calling_cb
        self._keys_by_value = {entry.key: key for key, entry in entries.items()}
        self._lock = threading.Lock()
        self.needed: list[str] = []
        # What the batch learned each virtual output holds, None where the store holds none, and the values read or flushed.
        self._digests: dict[str, str | None] = {}
        self._values: dict[str, object] = {}
        # The digest of the store's stamp once taken, None where it gave none.
        self._stamp: str | None = None
        self._is_stamped = False
        self._has_written = False

    def fetch_digests(self, keys: Iterable[str]) -> dict[str, str | None]:
        """Return the digest of each virtual output of `keys`, None where the store holds none: as recorded where the stamp matches the record under the same code, else as a read returns it. Raises StoreError."""
        with self._lock:
            unknown = [key for key in keys if key not in self._digests]
            if unknown:
                self._learn(unknown)
            return {key: self._digests[key] for key in keys}

    def fetch_value(self, key: str) -> object:
        """Return the value of the virtual output `key`, from memory or else from a read. Raises StoreError, and LookupError where the store holds none."""
        with self._lock:
            if key not in self._values:
                self._ensure_stamp()
                for read_key, (value, _) in self._read([*self.needed, key]).items():
                    self._values.setdefault(read_key, value)
            if key not in self._values:
                raise LookupError(f"{self._entries[key].text} holds no value")
            return self._values[key]

    def flush(self, changes: list[Change]) -> None:
        """Write `changes`, in order, then take the stamp, then read back every virtual output written or needed, failing where one written reads other than written, or one the batch knew changed. Raises StoreError."""
        with self._lock:
            changed = {change.key: change.value for change in changes}
            self._update(changed)
            self._has_written = True
            self._is_stamped = False
            self._ensure_stamp()
            read = self._read(list(dict.fromkeys([*self.needed, *changed])))
            for change in changes:
                found = read.get(change.key)
                text = self._entries[change.key].text
                if found is None:
                    raise StoreError(self._store, "read", f"left out {text}, which was written")
                if found[1] != change.digest:
                    reason = f"returned {text}, which differs from what was written"
                    raise StoreError(self._store, "read", reason)
            for key in self.needed:
                if key in changed or key not in self._digests:
                    continue
                found = read.get(key)
                if (None if found is None else found[1]) != self._digests[key]:
                    reason = f"found {self._entries[key].text} changed, though no rule wrote it"
                    raise StoreError(self._store, "read", reason)
            self._digests.update({key: None for key in self.needed})
            for key, (value, digest) in read.items():
                self._digests[key] = digest
                self._values[key] = value

    def build_record(self) -> StoreRecord | None:
        """Return what the state should hold of the store, or None where the batch took no stamp or learned nothing the state lacks."""
        with self._lock:
            if not self._is_stamped:
                return None
            digests = {key: digest or "" for key, digest in self._digests.items()}
            record = StoreRecord(self._stamp or "", self._store.code, digests)
        return None if record == self._recorded else record

    def _learn(self, unknown: list[str]) -> None:
        self._ensure_stamp()
        recorded = self._recorded
        if (
            recorded is not None
            and self._stamp is not None
            and recorded.stamp == self._stamp
            and recorded.code == self._store.code
        ):
            for key, digest in recorded.digests.items():
                if key in self._entries:
                    self._digests.setdefault(key, digest or None)
            unknown = [key for key in unknown if key not in self._digests]
            if not unknown:
                return
        read = self._read(list(dict.fromkeys([*self.needed, *unknown])))
        for key in [*self.needed, *unknown]:
            found = read.get(key)
            self._digests.setdefault(key, None if found is None else found[1])
        for key, (value, digest) in read.items():
            self._digests.setdefault(key, digest)
            self._values.setdefault(key, value)

    def _ensure_stamp(self) -> None:
        if self._is_stamped:
            return
        store = self._store
        if isinstance(store.value, FileStore):
            assert store.path is not None
            hashed = self._cache.fetch(store.path, Look.AGAIN)
            self._stamp = _ABSENT_FILE if hashed is None else hashed.digest
        else:
            stamp = self._call("stamp", _as_store(store).stamp)
            try:
                self._stamp = None if stamp is None else calc_value_digest(stamp)
            except UnhashableValueError as error:
                raise StoreError(
                    store,
                    "stamp",
                    f"returned a value of type {error.type_name}, which Facere can't hash, since {error.reason}",
                ) from None
        self._is_stamped = True

    def _read(self, keys: list[str]) -> dict[str, tuple[object, str]]:
        """Return each virtual output the store's read returns that a rule declares, by engine key, with its value and digest. Call it with the stamp taken."""
        store = self._store
        if isinstance(store.value, FileStore):
            if self._stamp == _ABSENT_FILE:
                return {}
            returned = self._read_file_store(store.value)
        else:
            wanted = [self._entries[key].key for key in dict.fromkeys(keys)]
            returned = self._call("read", lambda: _as_store(store).read(wanted))
        if not isinstance(returned, Mapping):
            raise StoreError(
                store, "read", f"returned a {type(returned).__qualname__}, not a mapping"
            )
        read = {}
        for value_key, value in returned.items():
            key = self._find_key(value_key)
            if key is None:
                continue
            try:
                read[key] = (value, calc_value_digest(value))
            except UnhashableValueError as error:
                raise StoreError(
                    store,
                    "read",
                    f"returned {self._entries[key].text} as a value of type {error.type_name}, which Facere can't hash, since {error.reason}",
                ) from None
        return read

    def _read_file_store(self, file_store: FileStore) -> object:
        """Return what the FileStore's read returns, or nothing where it raises before Facere first writes to it, since a file torn by an interrupted write costs rebuilds, never a stale record."""
        try:
            return self._call("read", file_store.read)
        except StoreError:
            if self._has_written:
                raise
            return {}

    def _find_key(self, value_key: object) -> str | None:
        try:
            return self._keys_by_value.get(value_key)
        except TypeError:
            return None

    def _update(self, changed: dict[str, object]) -> None:
        store = self._store
        if not isinstance(store.value, FileStore):
            by_value = {self._entries[key].key: value for key, value in changed.items()}
            self._call("update", lambda: _as_store(store).update(by_value))
            return
        file_store = store.value
        assert store.path is not None
        current: Mapping[Any, object] = {}
        if os.path.exists(store.path):
            returned = self._read_file_store(file_store)
            if isinstance(returned, Mapping):
                current = typing.cast("Mapping[Any, object]", returned)
        outputs = {}
        for key, entry in self._entries.items():
            if key in changed:
                outputs[entry.key] = changed[key]
            elif entry.key in current:
                outputs[entry.key] = current[entry.key]
        for value_key, value in current.items():
            outputs.setdefault(value_key, value)
        os.makedirs(os.path.dirname(store.path) or ".", exist_ok=True)
        self._call("write", lambda: file_store.write(outputs))

    def _call(self, method: str, call: Callable[[], object]) -> object:
        """Call one of the store's methods, raising StoreError where it raises or changes an attribute of the store."""
        self._calling_cb(True)
        try:
            result = call()
        except Exception as error:  # noqa: BLE001 - a store's code is the project's own
            raise StoreError(
                self._store, method, f"raised {type(error).__name__}", error
            ) from error
        finally:
            self._calling_cb(False)
        try:
            attributes = calc_value_digest(self._store.value)
        except UnhashableValueError:
            attributes = None
        if attributes != self._store.attributes:
            raise StoreError(self._store, method, "changed an attribute of the store")
        return result
