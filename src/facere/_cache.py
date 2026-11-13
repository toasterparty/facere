"""The hash cache, which pairs each file's hash with a stat taken before reading it, so an untouched file costs one stat, and the snapshot that a file a recipe first reports is compared against."""

import hashlib
import os
import posixpath
import stat
import sys
import time
from collections.abc import Iterator
from typing import NamedTuple

from facere._context import calc_path_key, is_within, iter_self_and_parents
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


class HashCache:
    """The hashes of files and directory trees, from `entries` where a stat vouches for one, and the paths fetched during this invocation.

    An entry is trusted where its stamp matches a stat of the file, it isn't racy, and its file system's timestamps prove something. A file fetched once in an invocation keeps its result until fetched again with `is_fresh`, so the invocation sees the files as they stood when it first looked.
    """

    def __init__(self, entries: dict[str, Entry]) -> None:
        self._entries = entries
        self._start_ns = time.time_ns()
        self._file_systems = FileSystems()
        self._fetched: dict[str, Hashed] = {}
        self._walked: set[str] = set()
        self._saved: dict[str, Entry] = {}
        self._removed: set[str] = set()

    def fetch(
        self, path: str, *, is_fresh: bool = False, new_files: list[str] | None = None
    ) -> Hashed | None:
        """Return the stamp and hash of the file or directory tree at `path`, or None where nothing is there.

        A path already fetched in this invocation returns what it did then, unless `is_fresh`. A file a tree holds that had no entry, so is new since the tree was last hashed, is added to `new_files` where given.
        """
        if not is_fresh:
            fetched = self._fetched.get(path)
            if fetched is not None:
                return fetched
        try:
            info = os.stat(path)
            if stat.S_ISDIR(info.st_mode):
                hashed = self._fetch_tree(path, frozenset({os.path.realpath(path)}), new_files)
            elif stat.S_ISREG(info.st_mode):
                hashed = self._fetch_file(path, info)
            else:
                hashed = Hashed(_calc_stamp(path, info)[0], "O")
        except FileNotFoundError:
            self._forget(path)
            return None
        self._fetched[path] = hashed
        return hashed

    def has_moved_since_fetched(self, path: str) -> bool:
        """Say whether the file at `path` changed since this invocation last fetched it, or was never fetched."""
        before = self._fetched.get(path)
        return before is None or self.fetch(path, is_fresh=True) != before

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
        changes = HashChanges(self._saved, frozenset(self._removed))
        self._saved = {}
        self._removed = set()
        return changes

    def _fetch_file(self, path: str, info: os.stat_result) -> Hashed:
        stamp, change_ns = _calc_stamp(path, info)
        entry = self._entries.get(path)
        if (
            entry is not None
            and entry.stamp == stamp
            and (path in self._fetched or not entry.is_racy)
            and self._file_systems.is_trusted(path, info)
        ):
            return Hashed(stamp, entry.digest)
        digest = _hash_file(path, info.st_mode)
        hashed_entry = Entry(stamp, digest, change_ns >= self._start_ns - _RACY_MARGIN_NS)
        if hashed_entry != entry:
            self._entries[path] = self._saved[path] = hashed_entry
            self._removed.discard(path)
        return Hashed(stamp, digest)

    def _fetch_tree(
        self, path: str, enclosing: frozenset[str], new_files: list[str] | None
    ) -> Hashed:
        """Return the stamp and hash of the tree at `path`, inside the resolved directories `enclosing`, which a link back into them must not enter again."""
        self._walked.add(path)
        digest = hashlib.sha256()
        stamps: list[tuple[str, Stamp]] = []
        with os.scandir(path) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
        for entry in entries:
            child = f"{path}/{entry.name}"
            try:
                hashed = self._fetch_entry(entry, child, enclosing, new_files)
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
        new_files: list[str] | None,
    ) -> Hashed:
        """Return the stamp and hash of what the tree entry `entry`, at `child`, names: a link that dangles or loops back into the tree as its text."""
        if entry.is_dir():
            resolved = os.path.realpath(child)
            if resolved in enclosing:
                return Hashed(_calc_link_stamp(child), "L" + os.readlink(child))
            return self._fetch_tree(child, enclosing | {resolved}, new_files)
        if entry.is_file():
            is_new = child not in self._entries
            hashed = self._fetch_file(child, os.stat(child))
            self._fetched[child] = hashed
            if is_new and new_files is not None:
                new_files.append(child)
            return hashed
        if entry.is_symlink():
            return Hashed(_calc_link_stamp(child), "L" + os.readlink(child))
        return Hashed(_calc_link_stamp(child), "O")

    def _forget(self, path: str) -> None:
        self._fetched.pop(path, None)
        if self._entries.pop(path, None) is not None:
            self._saved.pop(path, None)
            self._removed.add(path)

    def _drop_unwalked(self) -> None:
        """Drop the entry of each file inside a tree this invocation walked that no walk met or that is gone since, so the entries a tree holds are the files it held when last hashed."""
        if not self._walked:
            return
        gone = [
            path
            for path in self._entries
            if (path not in self._fetched or not os.path.lexists(path))
            and any(parent in self._walked for parent in iter_self_and_parents(path))
        ]
        for path in gone:
            self._forget(path)


class Snapshot:
    """The files under the root outside the output directory and hidden directories, as they stood before an invocation's first rule executed."""

    def __init__(self, cache: HashCache, out_dir: str) -> None:
        self._cache = cache
        self._out_dir = out_dir
        self._marks = {path: cache.fetch_mark(path) for path in iter_listed_files(out_dir)}
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
        directories = path.split("/")[:-1]
        if any(part.startswith(".") for part in directories):
            return False
        return not any(
            os.path.islink("/".join(directories[: index + 1])) for index in range(len(directories))
        )

    def _find_marks_by_key(self, key: str) -> list[str | None]:
        if self._paths_by_key is None:
            self._paths_by_key = {}
            for listed in self._marks:
                self._paths_by_key.setdefault(calc_path_key(listed), []).append(listed)
        return [self._marks[listed] for listed in self._paths_by_key.get(key, [])]


def iter_listed_files(out_dir: str) -> Iterator[str]:
    """Yield every file under the working directory, as normalize returns them, outside `out_dir` and any hidden directory, without entering a linked directory."""
    for directory, subdirectories, names in os.walk("."):
        relative = posixpath.normpath(directory.replace(os.sep, "/"))
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
