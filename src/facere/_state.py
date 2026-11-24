"""The state: a record of each rule's last success, or of the inputs that changed during its last execution, the hash cache, what each store held when last stamped, and what each watch's last cycle observed, kept in a SQLite database in the output directory.

The database is open only while it is read or written, so a task may delete the output directory on any OS. A database Facere can't read counts as empty, which costs only rebuilds, while one it can't write raises OSError. Writes skip fsync: a write lost to a crash costs a rebuild, since the next invocation re-verifies every output.
"""

import contextlib
import os
import sqlite3
import time
from collections.abc import Generator, Iterable
from typing import Any, NamedTuple

from facere._cache import Entry, HashChanges
from facere._engine import Trace

_SCHEMA_VERSION = 11
_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (outputs TEXT PRIMARY KEY, digest TEXT NOT NULL, inputs TEXT NOT NULL, output_hashes TEXT NOT NULL, added_inputs TEXT NOT NULL, added_names TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS listing (id INTEGER PRIMARY KEY CHECK (id = 0), paths TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS declared (id INTEGER PRIMARY KEY CHECK (id = 0), outputs TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS moved (outputs TEXT PRIMARY KEY, paths TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS hashes (path TEXT PRIMARY KEY, stamp TEXT NOT NULL, digest TEXT NOT NULL, is_racy INTEGER NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS observed (targets TEXT PRIMARY KEY, digest TEXT NOT NULL, files TEXT NOT NULL, dirs TEXT NOT NULL, outputs TEXT NOT NULL, saved_ns INTEGER NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS stores (store TEXT PRIMARY KEY, stamp TEXT NOT NULL, code TEXT NOT NULL, digests TEXT NOT NULL) WITHOUT ROWID;
"""
_SEPARATOR = "\0"
# How long a watch's observation outlives its last save, so the records of target lists no longer watched don't pile up. A watch still running after that long without a cycle keeps what it loaded, and its next cycle saves it again.
_OBSERVATION_LIFETIME_NS = 30 * 24 * 60 * 60 * 10**9
# Joins a directory's entries, since no file name holds it.
_ENTRY_SEPARATOR = "/"


class Record(NamedTuple):
    """A rule's last success. `trace` pairs each path its rule read and wrote with that path's hash, the inputs its recipe reported as those it found, and `added_names` holds the path key of the file name of each input reported, those outside the root included."""

    trace: Trace
    added_names: tuple[str, ...]


class StoreRecord(NamedTuple):
    """What a store held when last stamped: the digest of its stamp, `""` where it gave none, the digest of its code it was stamped under, and the digest of each virtual output by engine key, `""` where it held none."""

    stamp: str
    code: str
    digests: dict[str, str]


class Observation(NamedTuple):
    """What a cycle of a watch observed: the hash of each file it read as it found it, or `""` where none was there, the entries of each directory it listed, as calc_entries gives them, and which of those paths lie in a declared output. Paths are as normalize returns them."""

    files: dict[str, str]
    dirs: dict[str, tuple[str, ...]]
    outputs: frozenset[str]


class State(NamedTuple):
    """Everything load reads. `moved` holds, for each rule left unrecorded by its last execution, the inputs that changed during it. `declared` holds the output keys save_declared last saved, or None where it saved none, and `listing` the files save_listing last saved, read only where a record holds a file name a new file could shadow. `stores` holds each store's record by store id."""

    records: dict[tuple[str, ...], Record]
    moved: dict[tuple[str, ...], tuple[str, ...]]
    declared: frozenset[str] | None
    listing: frozenset[str]
    hashes: dict[str, Entry]
    stores: dict[str, StoreRecord]


def calc_key(outputs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(outputs))


def has_added_names(records: dict[tuple[str, ...], Record]) -> bool:
    """Say whether any record holds a file name a new file could shadow, which alone makes the tree's listing worth keeping."""
    return any(record.added_names for record in records.values())


def load(path: str) -> State:
    """Return the state, or an empty one where it is missing, unreadable, or of another schema."""
    empty = State({}, {}, None, frozenset(), {}, {})
    if not os.path.exists(path):
        return empty
    try:
        with contextlib.closing(sqlite3.connect(path)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                return empty
            return _read(connection)
    except sqlite3.DatabaseError:
        return empty


def save(path: str, key: tuple[str, ...], record: Record, changes: HashChanges) -> None:
    """Record the success of the rule outputting `key`, forgetting what save_moved kept of it, and save the hash cache's `changes`."""
    with _open(path) as connection:
        connection.execute("DELETE FROM moved WHERE outputs = ?", (_SEPARATOR.join(key),))
        trace = record.trace
        output_hashes = dict(trace.outputs)
        connection.execute(
            "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?, ?)",
            (
                _SEPARATOR.join(key),
                trace.digest,
                _join_pairs(trace.inputs),
                _SEPARATOR.join(output_hashes[output] for output in key),
                _join_pairs(trace.found),
                _SEPARATOR.join(record.added_names),
            ),
        )
        _write_hashes(connection, changes)


def remove(path: str, keys: list[tuple[str, ...]]) -> None:
    """Forget everything kept of the rules outputting `keys`."""
    if not keys or not os.path.exists(path):
        return
    joined = [(_SEPARATOR.join(key),) for key in keys]
    with _open(path) as connection:
        connection.executemany("DELETE FROM records WHERE outputs = ?", joined)
        connection.executemany("DELETE FROM moved WHERE outputs = ?", joined)


def save_stores(path: str, records: dict[str, StoreRecord]) -> None:
    """Replace the record of each store in `records`, by store id."""
    if not records:
        return
    with _open(path) as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO stores VALUES (?, ?, ?, ?)",
            [
                (store, record.stamp, record.code, _join_pairs(record.digests.items()))
                for store, record in records.items()
            ],
        )


def remove_stores(path: str, stores: Iterable[str]) -> None:
    """Forget what the state holds of each of `stores`, by store id."""
    removed = [(store,) for store in stores]
    if not removed or not os.path.exists(path):
        return
    with _open(path) as connection:
        connection.executemany("DELETE FROM stores WHERE store = ?", removed)


def save_moved(
    path: str, key: tuple[str, ...], paths: tuple[str, ...], changes: HashChanges
) -> None:
    """Keep the inputs `paths` that changed while the rule outputting `key` executed, which left it unrecorded, and save the hash cache's `changes`."""
    with _open(path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO moved VALUES (?, ?)",
            (_SEPARATOR.join(key), _SEPARATOR.join(paths)),
        )
        _write_hashes(connection, changes)


def save_hashes(path: str, changes: HashChanges) -> None:
    """Save the hash cache's `changes`, unless the state is gone, as after a task deleted the output directory."""
    if not os.path.exists(path) or not (changes.saved or changes.removed):
        return
    with _open(path) as connection:
        _write_hashes(connection, changes)


def save_listing(path: str, listing: frozenset[str]) -> None:
    """Replace the saved listing, unless the state is gone."""
    _save_paths(path, "INSERT OR REPLACE INTO listing VALUES (0, ?)", listing)


def save_declared(path: str, outputs: frozenset[str]) -> None:
    """Replace the saved output keys, unless the state is gone."""
    _save_paths(path, "INSERT OR REPLACE INTO declared VALUES (0, ?)", outputs)


def load_observation(path: str, targets: str) -> tuple[str, Observation] | None:
    """Return the digest save_observation was given for the watch of `targets` with its observation, or None where none is saved or the state can't be read."""
    row = _find_observed(path, "digest, files, dirs, outputs", targets)
    if row is None:
        return None
    digest, files, dirs, outputs = row
    entries = {
        path: tuple(joined.split(_ENTRY_SEPARATOR)) if joined else ()
        for path, joined in _pair(_split(dirs))
    }
    return digest, Observation(dict(_pair(_split(files))), entries, frozenset(_split(outputs)))


def fetch_observation_digest(path: str, targets: str) -> str | None:
    """Return the digest save_observation was given for the watch of `targets`, or None where none is saved or the state can't be read."""
    row = _find_observed(path, "digest", targets)
    return None if row is None else row[0]


def save_observation(path: str, targets: str, digest: str, observation: Observation) -> None:
    """Replace what the watch of `targets` observed, identified by `digest`, creating the state where it is gone, since a watch that built nothing yet still observed what to wait on. Drops the observation of every other watch whose last save is older than _OBSERVATION_LIFETIME_NS."""
    saved_ns = time.time_ns()
    with _open(path) as connection:
        connection.execute(
            "DELETE FROM observed WHERE targets != ? AND saved_ns < ?",
            (targets, saved_ns - _OBSERVATION_LIFETIME_NS),
        )
        connection.execute(
            "INSERT OR REPLACE INTO observed VALUES (?, ?, ?, ?, ?, ?)",
            (
                targets,
                digest,
                _join_pairs(sorted(observation.files.items())),
                _join_pairs(
                    (path, _ENTRY_SEPARATOR.join(entries))
                    for path, entries in sorted(observation.dirs.items())
                ),
                _SEPARATOR.join(sorted(observation.outputs)),
                saved_ns,
            ),
        )


def _read(connection: sqlite3.Connection) -> State:
    records = {}
    for outputs, digest, inputs, hashes, added, names in _fetch(
        connection,
        "SELECT outputs, digest, inputs, output_hashes, added_inputs, added_names FROM records",
    ):
        key = _split(outputs)
        trace = Trace(
            digest,
            _pair(_split(inputs)),
            tuple(zip(key, _split(hashes), strict=True)),
            _pair(_split(added)),
        )
        records[key] = Record(trace, _split(names))
    moved = {
        _split(outputs): _split(paths)
        for outputs, paths in _fetch(connection, "SELECT outputs, paths FROM moved")
    }
    declared = _read_paths(connection, "SELECT outputs FROM declared")
    is_listed = has_added_names(records)
    listing = _read_paths(connection, "SELECT paths FROM listing") if is_listed else None
    hashes = {
        path: Entry(stamp, digest, bool(is_racy))
        for path, stamp, digest, is_racy in _fetch(
            connection, "SELECT path, stamp, digest, is_racy FROM hashes"
        )
    }
    stores = {
        store: StoreRecord(stamp, code, dict(_pair(_split(digests))))
        for store, stamp, code, digests in _fetch(
            connection, "SELECT store, stamp, code, digests FROM stores"
        )
    }
    return State(records, moved, declared, listing or frozenset(), hashes, stores)


def _read_paths(connection: sqlite3.Connection, query: str) -> frozenset[str] | None:
    rows = _fetch(connection, query)
    return frozenset(_split(rows[0][0])) if rows else None


def _fetch(connection: sqlite3.Connection, query: str) -> list[Any]:
    return connection.execute(query).fetchall()


def _find_observed(path: str, columns: str, targets: str) -> tuple[str, ...] | None:
    """Return the `columns` saved for the watch of `targets`, or None where none is saved or the state can't be read."""
    if not os.path.exists(path):
        return None
    try:
        with contextlib.closing(sqlite3.connect(path)) as connection:
            query = f"SELECT {columns} FROM observed WHERE targets = ?"
            row = connection.execute(query, (targets,)).fetchone()
    except sqlite3.DatabaseError:
        return None
    return None if row is None else tuple(map(str, row))


def _write_hashes(connection: sqlite3.Connection, changes: HashChanges) -> None:
    connection.executemany(
        "DELETE FROM hashes WHERE path = ?", [(path,) for path in changes.removed]
    )
    connection.executemany(
        "INSERT OR REPLACE INTO hashes VALUES (?, ?, ?, ?)",
        [
            (path, entry.stamp, entry.digest, int(entry.is_racy))
            for path, entry in changes.saved.items()
        ],
    )


def _save_paths(path: str, statement: str, paths: frozenset[str]) -> None:
    if not os.path.exists(path):
        return
    with _open(path) as connection:
        connection.execute(statement, (_SEPARATOR.join(sorted(paths)),))


def _split(text: str) -> tuple[str, ...]:
    return tuple(text.split(_SEPARATOR)) if text else ()


def _pair(items: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(zip(items[::2], items[1::2], strict=True))


def _join_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    return _SEPARATOR.join(item for pair in pairs for item in pair)


@contextlib.contextmanager
def _open(path: str) -> Generator[sqlite3.Connection]:
    """Yield a connection that commits when the block succeeds, raising OSError when SQLite fails."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        try:
            connection = _connect(path)
        except sqlite3.DatabaseError:
            os.remove(path)
            connection = _connect(path)
        with contextlib.closing(connection), connection:
            yield connection
    except sqlite3.Error as error:
        raise OSError(f"{path}: {error}") from error


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA synchronous = OFF")
        if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
            drops = "".join(f'DROP TABLE "{name}"; ' for (name,) in tables.fetchall())
            connection.executescript(f"{drops}{_SCHEMA} PRAGMA user_version = {_SCHEMA_VERSION};")
        else:
            connection.executescript(_SCHEMA)
    except BaseException:
        connection.close()
        raise
    return connection
