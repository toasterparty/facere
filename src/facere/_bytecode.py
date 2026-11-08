"""The bytecode Python caches for the project's own modules, kept valid by a hash of each source."""

import _imp
import importlib.util
import os
import py_compile
import warnings
from collections.abc import Iterator

_CHECKED_HASH_FLAGS = 0b11


def ensure_checked(root: str) -> None:
    """Make each bytecode file cached under `sys.pycache_prefix` for a module under `root`, outside hidden directories, where a virtual environment lives, one Python validates by a hash of its source.

    Python trusts its default bytecode file on a source of the recorded size and whole-second mtime, so after a same-size edit within that second, a shared module would run its old code. Each other file is recompiled from the current source or removed, never trusted.
    """
    cached_root = os.path.dirname(importlib.util.cache_from_source(os.path.join(root, "fac.py")))
    is_hash_checked = _imp.check_hash_based_pycs != "never"
    for path in _iter_files(cached_root):
        if is_hash_checked and _is_checked_hash(path):
            continue
        if not is_hash_checked or not _try_recompile(path, root, cached_root):
            os.remove(path)


def _iter_files(cached_root: str) -> Iterator[str]:
    for directory, subdirectories, names in os.walk(cached_root):
        subdirectories[:] = [name for name in subdirectories if not name.startswith(".")]
        for name in names:
            yield os.path.join(directory, name)


def _is_checked_hash(path: str) -> bool:
    with open(path, "rb") as file:
        header = file.read(8)
    return len(header) == 8 and int.from_bytes(header[4:], "little") == _CHECKED_HASH_FLAGS


def _try_recompile(path: str, root: str, cached_root: str) -> bool:
    """Compile the source `path` caches into it as a checked hash-based file, and say whether that source exists, compiles, and is cached there at this interpreter's optimization level."""
    directory, name = os.path.split(os.path.relpath(path, cached_root))
    source = os.path.join(root, directory, f"{name.partition('.')[0]}.py")
    if importlib.util.cache_from_source(source) != path:
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            py_compile.compile(
                source,
                cfile=path,
                dfile=source,
                doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
            )
    except (OSError, py_compile.PyCompileError):
        return False
    return True
