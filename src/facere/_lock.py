"""The lock that makes a second invocation on one output directory wait for the first.

The kernel gives it back when its holder exits or is killed, so none goes stale: `flock` on a file in `/tmp` on POSIX, and a named mutex on Windows. Neither name comes from the environment, so no variable makes two invocations miss each other.
"""

import contextlib
import hashlib
import os
import sys
import time
from collections.abc import Callable, Iterator

from facere._diagnostics import Diagnostic, FacereError

_PID_FILE_NAME = "lock.pid"
_RETRY_S = 0.05
_KEY_CHARS = 32
_LOCK_DIR = "/tmp"  # noqa: S108 - shared by every user and never read from TMPDIR, by design


class LockTimeoutError(Exception):
    """Another invocation still held the output directory when the wait the user allowed ran out."""


class OutputLock:
    """The exclusive hold of one output directory, named `out_dir` in messages, whose state lies in the absolute `state_dir`.

    Take and give it on one thread, since Windows ties a mutex to the thread that took it. While it holds the lock, the holder keeps its PID in the state directory, only so that a waiting invocation can name it, and as it gives the lock removes that file with each directory made for it that is still empty, so an invocation that built nothing leaves nothing.
    """

    def __init__(self, out_dir: str, state_dir: str) -> None:
        self._out_dir = out_dir
        self._pid_file = os.path.join(state_dir, _PID_FILE_NAME)
        resolved = os.path.normcase(os.path.realpath(os.path.dirname(state_dir)))
        self._key = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:_KEY_CHARS]
        self._handle: int | None = None
        self._made_dirs: list[str] = []

    @property
    def is_held(self) -> bool:
        return self._handle is not None

    def take(self, timeout_s: float | None, wait_cb: Callable[[int | None], None]) -> None:
        """Wait for the lock, as long as it takes, or raise LockTimeoutError after `timeout_s` seconds.

        `wait_cb` is called once if the lock is held, with its holder's PID, or None where that is unknown. Raises FacereError at once where the holder is this process or one that started it, which would never give the lock.
        """
        assert self._handle is None
        deadline_s = None if timeout_s is None else time.monotonic() + timeout_s
        has_waited = False
        checked_holder = None
        while (handle := _try_take(self._key)) is None:
            holder = self._read_holder()
            # Each holder is checked once, since without /proc walking the ancestors runs ps for each.
            if holder is not None and holder != checked_holder:
                if holder == os.getpid() or holder in _iter_ancestors():
                    message = f"the invocation with PID {holder}, which started this one, holds the output directory {self._out_dir}, so waiting for it would never end"
                    raise FacereError(Diagnostic(None, message))
                checked_holder = holder
            remaining_s = _RETRY_S if deadline_s is None else deadline_s - time.monotonic()
            if remaining_s <= 0:
                waited = f"after {timeout_s:g} second{'' if timeout_s == 1 else 's'}"
                raise LockTimeoutError(
                    f"{_describe(holder)} still held the output directory {self._out_dir} {waited}"
                )
            if not has_waited:
                wait_cb(holder)
                has_waited = True
            time.sleep(min(_RETRY_S, remaining_s))
        self._handle = handle
        with contextlib.suppress(OSError):
            self._made_dirs = _make_dirs(os.path.dirname(self._pid_file))
            with open(self._pid_file, "w", encoding="utf-8") as file:
                file.write(str(os.getpid()))

    def give(self) -> None:
        """Let the next invocation in. Giving a lock not held does nothing."""
        if self._handle is None:
            return
        # Removed while still held, so no waiter reads this PID as the next holder's.
        with contextlib.suppress(OSError):
            os.remove(self._pid_file)
        for directory in reversed(self._made_dirs):
            with contextlib.suppress(OSError):
                os.rmdir(directory)
        _give(self._key, self._handle)
        self._handle = None

    def _read_holder(self) -> int | None:
        try:
            with open(self._pid_file, encoding="utf-8") as file:
                return int(file.read())
        except (OSError, ValueError):
            return None


def describe_wait(holder: int | None, out_dir: str) -> str:
    """Return the line an invocation prints once as it starts to wait for the lock on `out_dir`."""
    return f"waiting for {_describe(holder)}, which holds the output directory {out_dir}"


def _make_dirs(directory: str) -> list[str]:
    """Make `directory` with each directory above it that is missing, and return those made, outermost first."""
    missing = []
    while not os.path.isdir(directory):
        missing.append(directory)
        directory = os.path.dirname(directory)
    made = []
    for path in reversed(missing):
        # Collection may make the same directory at this moment, for its bytecode.
        with contextlib.suppress(FileExistsError):
            os.mkdir(path)
            made.append(path)
    return made


def _describe(holder: int | None) -> str:
    return "another invocation" if holder is None else f"the invocation with PID {holder}"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _kernel32.ReleaseMutex.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    _WAIT_OBJECT_0 = 0x0
    # The last holder died holding it, which gives the mutex to the next waiter all the same.
    _WAIT_ABANDONED = 0x80
    _SNAPSHOT_PROCESSES = 0x2
    _INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    _MAX_PATH = 260

    class _ProcessEntry(ctypes.Structure):
        _fields_ = (
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("process_id", wintypes.DWORD),
            ("default_heap_id", ctypes.c_size_t),
            ("module_id", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent_process_id", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe_file", wintypes.WCHAR * _MAX_PATH),
        )

    _kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    _kernel32.Process32FirstW.restype = wintypes.BOOL
    _kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    _kernel32.Process32NextW.restype = wintypes.BOOL

    def _try_take(key: str) -> int | None:
        """Return a handle on the mutex `key` names, owned by the calling thread, or None where another thread or process owns it."""
        handle = _kernel32.CreateMutexW(None, False, f"Local\\facere-{key}")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if _kernel32.WaitForSingleObject(handle, 0) in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            return int(handle)
        _kernel32.CloseHandle(handle)
        return None

    def _give(key: str, handle: int) -> None:
        _kernel32.ReleaseMutex(handle)
        _kernel32.CloseHandle(handle)

    def _iter_ancestors() -> Iterator[int]:
        """Yield the PID of each process that started this one, nearest first, as far as the process list still holds them."""
        snapshot = _kernel32.CreateToolhelp32Snapshot(_SNAPSHOT_PROCESSES, 0)
        if snapshot == _INVALID_HANDLE_VALUE:
            return
        parents: dict[int, int] = {}
        try:
            entry = _ProcessEntry()
            entry.size = ctypes.sizeof(_ProcessEntry)
            has_entry = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                parents[entry.process_id] = entry.parent_process_id
                has_entry = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snapshot)
        # Windows reuses a dead parent's PID, so the chain can loop.
        seen = {os.getpid()}
        pid = parents.get(os.getpid())
        while pid is not None and pid not in seen:
            yield pid
            seen.add(pid)
            pid = parents.get(pid)

else:
    import fcntl

    _PROC_STAT_PARENT_FIELD = 1

    def _try_take(key: str) -> int | None:
        """Return a descriptor holding `flock` on the file `key` names, or None where another descriptor holds it."""
        path = _calc_lock_path(key)
        while True:
            descriptor = _open_lock_file(path)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(descriptor)
                return None
            except BaseException:
                os.close(descriptor)
                raise
            # A holder removes the file as it gives the lock, so a lock on a file since removed or replaced holds nothing.
            if _is_at(descriptor, path):
                return descriptor
            os.close(descriptor)

    def _give(key: str, handle: int) -> None:
        path = _calc_lock_path(key)
        with contextlib.suppress(OSError):
            if _is_at(handle, path):
                os.remove(path)
        os.close(handle)

    def _calc_lock_path(key: str) -> str:
        return os.path.join(_LOCK_DIR, f"facere-{key}.lock")

    def _open_lock_file(path: str) -> int:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        # Linux refuses O_CREAT on another user's file in a sticky directory, so an existing file is opened without it.
        with contextlib.suppress(FileNotFoundError):
            return os.open(path, flags)
        return os.open(path, flags | os.O_CREAT, 0o644)

    def _is_at(descriptor: int, path: str) -> bool:
        try:
            return os.path.samestat(os.fstat(descriptor), os.stat(path, follow_symlinks=False))
        except FileNotFoundError:
            return False

    def _iter_ancestors() -> Iterator[int]:
        """Yield the PID of each process that started this one, nearest first."""
        pid = os.getppid()
        while pid > 1:
            yield pid
            parent = _find_parent(pid)
            if parent is None:
                return
            pid = parent

    def _find_parent(pid: int) -> int | None:
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as file:
                # The fields after the command's name, which may itself hold spaces and parentheses.
                fields = file.read().rpartition(")")[2].split()
            return int(fields[_PROC_STAT_PARENT_FIELD])
        except (OSError, ValueError, IndexError):
            pass
        # No /proc, as on macOS.
        import subprocess

        try:
            listed = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],  # noqa: S607 - ps is found on PATH
                capture_output=True,
                text=True,
                check=False,
            )
            return int(listed.stdout)
        except (OSError, ValueError):
            return None
