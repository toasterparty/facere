"""The threads recipes execute on, and the main thread's wait on them, since only the main thread receives the signals that end a build early."""

import contextlib
import signal
import sys
import threading
from collections.abc import Callable, Generator
from types import FrameType

# A signal handler only sets a flag, since taking a lock inside one can deadlock, so the main thread wakes this often
# to read it. On Windows it also could not be interrupted while it waits.
WAKE_S = 0.05


class Signals:
    """What signals asked of the invocation: `is_stop_requested` once one asked for a graceful stop, and `is_hung_up` once the terminal closed."""

    def __init__(self) -> None:
        self.is_stop_requested = False
        self.is_hung_up = False

    def on_stop(self, signum: int, frame: FrameType | None) -> None:
        self.is_stop_requested = True

    def on_hangup(self, signum: int, frame: FrameType | None) -> None:
        self.is_hung_up = True
        raise KeyboardInterrupt


@contextlib.contextmanager
def watch_signals() -> Generator[Signals]:
    """Yield what signals ask for the length of the block: a graceful stop on SIGTERM, or on Windows CTRL_BREAK_EVENT, and on SIGHUP an interrupt, as SIGINT raises.

    Only the main thread can watch signals, so on any other the block sees none.
    """
    signals = Signals()
    if threading.current_thread() is not threading.main_thread():
        yield signals
        return
    if sys.platform == "win32":
        handlers = {signal.SIGBREAK: signals.on_stop}
    else:
        handlers = {signal.SIGTERM: signals.on_stop, signal.SIGHUP: signals.on_hangup}
    saved = {signum: signal.signal(signum, handler) for signum, handler in handlers.items()}
    try:
        yield signals
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)


class Crew:
    """The threads that work for one batch, at most `calc_jobs()` of them at once, a count asked for only once a second thread is wanted."""

    def __init__(self, calc_jobs: Callable[[], int]) -> None:
        self._calc_jobs = calc_jobs
        self._jobs: int | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._started = 0
        self._ended = 0

    def try_add(self, work: Callable[[], None]) -> bool:
        """Start a thread calling `work`, which must raise nothing, or return False where as many as may run already do. Any thread may call it."""
        with self._lock:
            working = self._started - self._ended
            if working and self._jobs is None:
                self._jobs = self._calc_jobs()
            if working and self._jobs is not None and working >= self._jobs:
                return False
            self._started += 1
        # A daemon, so an interrupt ends the process though a recipe's own Python runs on.
        threading.Thread(target=self._run, args=(work,), daemon=True).start()
        return True

    def wake(self) -> None:
        """End the main thread's current wait early."""
        self._wake.set()

    def wait(self, wake_cb: Callable[[], bool]) -> bool:
        """Wait on the main thread until every thread started has ended, calling `wake_cb` each time the wait wakes, and return whether they all ended before `wake_cb` returned False to give up on them."""
        while not self._has_ended():
            self._wake.wait(WAKE_S)
            self._wake.clear()
            if not wake_cb():
                return self._has_ended()
        return True

    def _has_ended(self) -> bool:
        with self._lock:
            return self._ended == self._started

    def _run(self, work: Callable[[], None]) -> None:
        try:
            work()
        finally:
            with self._lock:
                self._ended += 1
            self._wake.set()
