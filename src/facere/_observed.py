"""What a cycle of a watch observed, saved in the state so the watch knows what to poll: each file it read with the hash of what it found, each directory it listed with its entries, and which of those lie in a declared output, so the watch tells Facere's own writes from an edit.

Only a cycle records it, since an invocation that built nothing leaves no output directory, while a cycle must leave what to wait on. A hidden path is never kept, so it never starts a cycle.
"""

import hashlib
import os
import time
from collections.abc import Iterable

from facere import _state
from facere._cache import HashCache, calc_entries, fetch_file_stamp
from facere._context import Context, is_under_root, is_within, normalize

ABSENT = ""
"""The hash of a file that was not there."""
# The hash of a file collection read that changed before it was hashed. It matches no content, so the watch starts a
# cycle at once.
_MOVED = "?"


class Observed:
    """What one invocation observed, through all its batches, for the watch of `targets`.

    `files` holds each file's hash, `dirs` each directory's entries, as calc_entries gives them, and `outputs` the paths among them that lie in a declared output. `reads` holds each file collection opened that awaits its hash, with the stamp it had as it was opened, or None where nothing was there. Once a collection fails, `is_extending` holds, and the saved observation is extended rather than replaced, so the watch still waits on what the last collected cycle observed.
    """

    __slots__ = ("dirs", "files", "is_extending", "outputs", "reads", "saved_digest", "targets")

    def __init__(self, targets: list[str]) -> None:
        self.targets = calc_watch_key(targets)
        self.files: dict[str, str] = {}
        self.dirs: dict[str, tuple[str, ...]] = {}
        self.outputs: set[str] = set()
        self.reads: dict[str, str | None] = {}
        self.is_extending = False
        self.saved_digest: str | None = None

    def add(
        self,
        files: dict[str, str],
        dirs: dict[str, tuple[str, ...]],
        absent: Iterable[str],
        outputs: set[str],
        excluded: Iterable[str],
    ) -> None:
        """Add what a batch observed, which replaces what an earlier batch saw of the same path, leaving out `excluded`, the outputs of rules that failed, since what a failed recipe left is stale whatever its content. Call it before resolve_reads, whose hashes it must not replace."""
        for path in absent:
            if path not in files:
                self.files[path] = ABSENT
        # A file collection read that changed since stays changed until a collection reads it again.
        for path, digest in files.items():
            if self.files.get(path) != _MOVED:
                self.files[path] = digest
        self.dirs.update(dirs)
        self.outputs |= outputs
        for path in excluded:
            self.files.pop(path, None)
            self.dirs.pop(path, None)
            self.outputs.discard(path)

    def add_absent(self, path: str) -> None:
        """Keep `path` as a file that was not there, unless something was seen of it."""
        self.files.setdefault(path, ABSENT)

    def resolve_reads(self, cache: HashCache) -> None:
        """Give each file collection opened the hash `cache` finds, or where it changed since it was opened, one that matches no content."""
        for path, stamp in self.reads.items():
            hashed = cache.fetch(path)
            if hashed is None:
                self.files[path] = ABSENT if stamp is None else _MOVED
            else:
                self.files[path] = hashed.digest if hashed.stamp == stamp else _MOVED
        self.reads.clear()

    def save(self, state_path: str) -> None:
        """Save what was observed as the watch's observation, unless it is what was saved already, hashing afresh the files collection opened that no build hashed. Raises OSError where the state can't be written."""
        if self.reads:
            self.resolve_reads(HashCache({}, time.time_ns()))
        observation = _state.Observation(
            {path: digest for path, digest in self.files.items() if not _is_hidden(path)},
            {path: digest for path, digest in self.dirs.items() if not _is_hidden(path)},
            frozenset(path for path in self.outputs if not _is_hidden(path)),
        )
        saved = None
        if self.is_extending or self.saved_digest is None:
            saved = _state.load_observation(state_path, self.targets)
        if self.is_extending and saved is not None:
            observation = _merge(saved[1], observation)
        digest = _calc_digest(observation)
        if digest != self.saved_digest and (saved is None or saved[0] != digest):
            _state.save_observation(state_path, self.targets, digest, observation)
        self.saved_digest = digest


def calc_watch_key(targets: list[str]) -> str:
    """Return what a watch of `targets` saves its observation under, so watches of other targets on one output directory keep their own."""
    return "\0".join(targets)


def note_read(observed: Observed, context: Context, path: str) -> None:
    """Keep the stamp of the file at the absolute `path`, which collection is about to open, where it is the project's own: under the root, outside the output directory, and in no hidden directory."""
    relative = _find_project_path(context, path)
    if relative is None or relative in observed.reads or os.path.isdir(path):
        return
    observed.reads[relative] = fetch_file_stamp(path)


def note_listed(observed: Observed, context: Context, path: str) -> None:
    """Keep calc_entries of the directory at the absolute `path`, which collection is about to list, where it is the project's own. Listed first, so an entry added before collection lists it starts a cycle rather than going unseen."""
    relative = _find_project_path(context, path)
    if relative is None or relative in observed.dirs:
        return
    try:
        names = os.listdir(path)
    except OSError:
        return
    observed.dirs[relative] = calc_entries(names)


def _find_project_path(context: Context, path: str) -> str | None:
    if not is_under_root(path, context.root):
        return None
    relative = normalize(path, context.root)
    if is_within(relative, context.out_dir) or _is_hidden(relative):
        return None
    return relative


def _is_hidden(path: str) -> bool:
    """Say whether `path`, as normalize returns it, lies in a hidden directory or names a hidden file."""
    return any(part.startswith(".") and part not in (".", "..") for part in path.split("/"))


def _merge(saved: _state.Observation, observation: _state.Observation) -> _state.Observation:
    return _state.Observation(
        {**saved.files, **observation.files},
        {**saved.dirs, **observation.dirs},
        saved.outputs | observation.outputs,
    )


def _calc_digest(observation: _state.Observation) -> str:
    text = repr(
        (
            sorted(observation.files.items()),
            sorted(observation.dirs.items()),
            sorted(observation.outputs),
        )
    )
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()
