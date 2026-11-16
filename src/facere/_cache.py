"""The hash cache, which pairs each file's hash with a stat taken before reading it, so an untouched file costs one stat, and the snapshot that a file a recipe first reports is compared against."""

import enum
import hashlib
import os
import posixpath
import stat
import sys
import threading
from collections.abc import Iterator
from typing import NamedTuple

from facere._context import (
    STATE_DIR_NAME,
    calc_path_key,
    holds_state,
    is_within,
    iter_self_and_parents,
)
from facere._filesystem import FileSystems
from facere._hash import feed

if sys.platform == "win32":
    from facere._filesystem import read_change_time_ns

# Timestamp granularity can't be known, from a timer tick to FAT's 2 s, so the margin is fixed.
_RACY_MARGIN_NS = 2_000_000_000

Stamp = str | tuple[object, ...]
"""What a stat shows of a file, or for a directory, of every entry in its tree, so a change shows as a different stamp even where the content ends as it was."""


class Entry(NamedTuple):
    """A file's hash with the stamp of the stat taken before reading it. `is_racy` holds where the file last changed within the margin before the start of the invocation that hashed it, so a change since could have left the stamp as it was."""

    stamp: str
    digest: str
    is_racy: bool


class Hashed(NamedTuple):
    stamp: Stamp
    digest: str


class HashChanges(NamedTuple):
    """The entries a cache added or replaced, and the paths whose entries it dropped, since it last gave its changes."""

    saved: dict[str, Entry]
    removed: frozenset[str]


class Look(enum.Enum):
    """What a fetch does where the session already saw the path.

    Only FIRST and AGAIN decide what the session saw, which is what the dependency engine was told. A CHECK compares against that, so however many recipes execute at once, none moves what another compares against.
    """

    FIRST = enum.auto()
    """Return what the session first saw, reading the path only if it saw nothing."""
    AGAIN = enum.auto()
    """Read the path now, and keep that as what the session saw."""
    CHECK = enum.auto()
    """Read the path now, leaving what the session saw."""


class HashCache:
    """The hashes of files and directory trees, from `entries` where a stat vouches for one, and what this session saw of each path.

    An entry is trusted where its stamp matches a stat of the file, it isn't racy, and its file system's timestamps prove something. `start_ns` is the clock's reading as the session started, which decides what is racy. Any thread may call any method: one lock guards the changes to save, and is never held while a file is read.
    """

    def __init__(self, entries: dict[str, Entry], start_ns: int) -> None:
        self._entries = entries
        self._start_ns = start_ns
        self._file_systems = FileSystems()
        self._lock = threading.Lock()
        self._seen: dict[str, Hashed] = {}
        self._walked: set[str] = set()
        self._saved: dict[str, Entry] = {}
        self._removed: set[str] = set()

    def fetch(
        self, path: str, look: Look = Look.FIRST, new_files: list[str] | None = None
    ) -> Hashed | None:
        """Return the stamp and hash of the file or directory tree at `path`, or None where nothing is there.

        A file a tree holds that had no entry, so is new since the tree was last hashed, is added to `new_files` where given.
        """
        if look is Look.FIRST:
            # One lookup, which a dict makes atomic with or without the GIL, so the common case takes no lock.
            seen = self._seen.get(path)
            if seen is not None:
                return seen
        try:
            info = os.stat(path)
            if stat.S_ISDIR(info.st_mode):
                enclosing = frozenset({os.path.realpath(path)})
                hashed = self._fetch_tree(path, enclosing, look, new_files)
                if look is not Look.CHECK:
                    with self._lock:
                        self._seen[path] = hashed
                return hashed
            if stat.S_ISREG(info.st_mode):
                return self._fetch_file(path, info, look is not Look.CHECK)
            hashed = Hashed(_calc_stamp(path, info)[0], "O")
        except FileNotFoundError:
            if look is not Look.CHECK:
                self._forget(path)
            return None
        with self._lock:
            if look is Look.FIRST:
                return self._seen.setdefault(path, hashed)
            if look is Look.AGAIN:
                self._seen[path] = hashed
        return hashed

    def has_moved(self, path: str) -> bool:
        """Say whether the file at `path` differs from what the session saw of it, or was never seen."""
        with self._lock:
            seen = self._seen.get(path)
        return seen is None or self.fetch(path, Look.CHECK) != seen

    def fetch_mark(self, path: str) -> str | None:
        """Return what shows a change to the file at `path` without its old content: its stamp, or where its file system's timestamps prove nothing, its hash. None where nothing is there."""
        try:
            info = os.stat(path)
            if self._file_systems.is_trusted(path, info):
                return _calc_stamp(path, info)[0]
            return _hash_file(path, info.st_mode)
        except OSError:
            return None

    def take_changes(self, *, is_final: bool = False) -> HashChanges:
        """Return the changes since the last call, and forget them. Where `is_final`, also drop the entries of files gone from the trees walked."""
        if is_final:
            self._drop_unwalked()
        with self._lock:
            changes = HashChanges(self._saved, frozenset(self._removed))
            self._saved = {}
            self._removed = set()
        return changes

    def _fetch_file(self, path: str, info: os.stat_result, is_kept: bool) -> Hashed:
        """Return the stamp and hash of the file at `path`, which `info` describes, keeping it as what the session saw where `is_kept`."""
        stamp, change_ns = _calc_stamp(path, info)
        # A trusted entry costs no lock: each step reads or writes one table entry, which a dict makes atomic with
        # or without the GIL, and two threads fetching one path at once each return what they saw.
        seen = self._seen.get(path)
        entry = self._entries.get(path)
        is_vouched = (
            entry is not None
            and entry.stamp == stamp
            and (seen is not None or not entry.is_racy)
            and self._file_systems.is_trusted(path, info)
        )
        if is_vouched:
            assert entry is not None
            hashed = Hashed(stamp, entry.digest)
            if is_kept:
                self._seen[path] = hashed
            return hashed
        digest = _hash_file(path, info.st_mode)
        hashed = Hashed(stamp, digest)
        hashed_entry = Entry(stamp, digest, change_ns >= self._start_ns - _RACY_MARGIN_NS)
        with self._lock:
            if hashed_entry != self._entries.get(path):
                self._entries[path] = self._saved[path] = hashed_entry
                self._removed.discard(path)
            if is_kept:
                self._seen[path] = hashed
        return hashed

    def _fetch_tree(
        self, path: str, enclosing: frozenset[str], look: Look, new_files: list[str] | None
    ) -> Hashed:
        """Return the stamp and hash of the tree at `path`, inside the resolved directories `enclosing`, which a link back into them must not enter again. The files it holds are each read now, whatever the session saw."""
        with self._lock:
            self._walked.add(path)
        digest = hashlib.sha256()
        stamps: list[tuple[str, Stamp]] = []
        with os.scandir(path) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
        for entry in entries:
            child = f"{path}/{entry.name}"
            try:
                hashed = self._fetch_entry(entry, child, enclosing, look, new_files)
            except FileNotFoundError:
                continue
            feed(digest, b"N", entry.name.encode("utf-8", "surrogateescape"))
            feed(digest, b"C", hashed.digest.encode("utf-8", "surrogateescape"))
            stamps.append((entry.name, hashed.stamp))
        return Hashed(tuple(stamps), "D" + digest.hexdigest())

    def _fetch_entry(
        self,
        entry: os.DirEntry[str],
        child: str,
        enclosing: frozenset[str],
        look: Look,
        new_files: list[str] | None,
    ) -> Hashed:
        """Return the stamp and hash of what the tree entry `entry`, at `child`, names: a link that dangles or loops back into the tree as its text."""
        if entry.is_dir():
            resolved = os.path.realpath(child)
            if resolved in enclosing:
                return _hash_link(child)
            return self._fetch_tree(child, enclosing | {resolved}, look, new_files)
        if entry.is_file():
            with self._lock:
                is_new = child not in self._entries
            hashed = self._fetch_file(child, os.stat(child), look is not Look.CHECK)
            if is_new and new_files is not None:
                new_files.append(child)
            return hashed
        if entry.is_symlink():
            return _hash_link(child)
        return Hashed(_calc_link_stamp(child), "O")

    def _forget(self, path: str) -> None:
        with self._lock:
            self._forget_locked(path)

    def _forget_locked(self, path: str) -> None:
        self._seen.pop(path, None)
        if self._entries.pop(path, None) is not None:
            self._saved.pop(path, None)
            self._removed.add(path)

    def _drop_unwalked(self) -> None:
        """Drop the entry of each file inside a tree this session walked that no walk kept or that is gone since, so the entries a tree holds are the files it held when last hashed."""
        with self._lock:
            if not self._walked:
                return
            candidates = [
                path
                for path in self._entries
                if any(parent in self._walked for parent in iter_self_and_parents(path))
            ]
            unseen = [path for path in candidates if path not in self._seen]
        gone = [path for path in candidates if not os.path.lexists(path)]
        with self._lock:
            for path in (*unseen, *gone):
                self._forget_locked(path)


class Snapshot:
    """The files under the root outside the output directory and hidden directories, as they stood before a session's first rule executed. Any thread may ask it."""

    def __init__(self, cache: HashCache, out_dir: str) -> None:
        self._cache = cache
        self._out_dir = out_dir
        self._marks = {path: cache.fetch_mark(path) for path in iter_listed_files(out_dir)}
        self._lock = threading.Lock()
        self._paths_by_key: dict[str, list[str]] | None = None

    def has_moved(self, path: str) -> bool:
        """Say whether the file at `path`, as normalize returns it, changed since the snapshot or is new since, where the snapshot can tell. A file outside the root, or in a directory the listing never enters, counts as unchanged."""
        if path in self._marks:
            mark = self._cache.fetch_mark(path)
            return mark is None or mark != self._marks[path]
        if not self._is_listed(path):
            return False
        # On a file system that ignores case, a report may spell a file the listing holds differently.
        mark = self._cache.fetch_mark(path)
        return mark is None or mark not in self._find_marks_by_key(calc_path_key(path))

    def _is_listed(self, path: str) -> bool:
        if os.path.isabs(path) or path == ".." or path.startswith("../"):
            return False
        if is_within(path, self._out_dir):
            return False
        directory = posixpath.dirname(path)
        if any(part.startswith(".") for part in directory.split("/")):
            return False
        return not any(
            os.path.islink(parent) or holds_state(parent)
            for parent in iter_self_and_parents(directory)
        )

    def _find_marks_by_key(self, key: str) -> list[str | None]:
        with self._lock:
            if self._paths_by_key is None:
                self._paths_by_key = {}
                for listed in self._marks:
                    self._paths_by_key.setdefault(calc_path_key(listed), []).append(listed)
            paths = self._paths_by_key.get(key, [])
        return [self._marks[listed] for listed in paths]


def iter_listed_files(out_dir: str) -> Iterator[str]:
    """Yield every file under the working directory, as normalize returns them, outside `out_dir`, any other directory holding Facere's state, and any hidden directory, without entering a linked directory."""
    for directory, subdirectories, names in os.walk("."):
        relative = posixpath.normpath(directory.replace(os.sep, "/"))
        if relative != "." and STATE_DIR_NAME in subdirectories and holds_state(relative):
            subdirectories.clear()
            continue
        subdirectories[:] = [
            name
            for name in subdirectories
            if not name.startswith(".")
            and not is_within(posixpath.normpath(posixpath.join(relative, name)), out_dir)
        ]
        for name in names:
            yield posixpath.normpath(posixpath.join(relative, name))


def _calc_stamp(path: str, info: os.stat_result) -> tuple[str, int]:
    """Return the stamp of the file at `path` that `info` describes, and when it last changed, its content or metadata."""
    change_ns = read_change_time_ns(path) if sys.platform == "win32" else info.st_ctime_ns
    return _format_stamp(info, change_ns), max(info.st_mtime_ns, change_ns)


def _hash_link(path: str) -> Hashed:
    return Hashed(_calc_link_stamp(path), "L" + os.readlink(path))


def _calc_link_stamp(path: str) -> str:
    """Return the stamp of the link at `path` itself, which on Windows leaves out the change time, since reading it would follow the link."""
    info = os.lstat(path)
    return _format_stamp(info, info.st_ctime_ns)


def _format_stamp(info: os.stat_result, change_ns: int) -> str:
    return f"{info.st_size}:{info.st_mtime_ns}:{change_ns}:{info.st_ino}:{info.st_mode}"


def _hash_file(path: str, mode: int) -> str:
    """Return a digest of the file's bytes and, outside Windows, its executable bit."""
    with open(path, "rb") as file:
        content = hashlib.file_digest(file, "sha256").hexdigest()
    is_executable = sys.platform != "win32" and bool(mode & stat.S_IXUSR)
    return ("X" if is_executable else "F") + content
