"""A status row pinned to the bottom of the terminal, below the scrolling output of the commands a build runs."""

import contextlib
import os
import signal
import sys
import threading
from collections.abc import Callable, Generator
from types import FrameType
from typing import TextIO

_CSI = "\x1b["
_SAVE_CURSOR = "\x1b7"
_RESTORE_CURSOR = "\x1b8"
_MIN_ROWS = 3


@contextlib.contextmanager
def pin_status(stream: TextIO) -> Generator[Callable[[str], None]]:
    """Yield a function that shows its text on the bottom row of `stream`'s terminal, scrolling everything else above it.

    Only a terminal on a POSIX system gets the row, and anything else gets a function that does nothing. The row is erased and the scroll region restored on exit, including when a signal ends the process.
    """
    row = _StatusRow(stream)
    row.enable()
    try:
        yield row.show
    finally:
        row.disable()


class _StatusRow:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._text = ""
        self._rows = 0
        self._cols = 0
        self._is_enabled = False
        self._saved_handlers: dict[
            int, signal.Handlers | Callable[[int, FrameType | None], object] | int | None
        ] = {}

    def enable(self) -> None:
        if sys.platform == "win32" or not self._can_pin():
            return
        size = self._try_fetch_size()
        if size is None:
            return
        self._cols, self._rows = size
        self._is_enabled = True
        self._write(f"\n{_SAVE_CURSOR}{self._calc_region()}{_RESTORE_CURSOR}{_CSI}1A")
        self._saved_handlers = {
            signum: signal.signal(signum, handler)
            for signum, handler in (
                (signal.SIGWINCH, self._on_resize),
                (signal.SIGTERM, self._on_kill),
                (signal.SIGHUP, self._on_kill),
            )
        }

    def disable(self) -> None:
        if not self._is_enabled:
            return
        self._is_enabled = False
        for signum, handler in self._saved_handlers.items():
            signal.signal(signum, handler)
        self._write(f"{_SAVE_CURSOR}{self._calc_clear()}{_CSI}r{_RESTORE_CURSOR}")

    def show(self, text: str) -> None:
        self._text = text
        if self._is_enabled:
            self._write(f"{_SAVE_CURSOR}{self._calc_draw()}{_RESTORE_CURSOR}")

    def _can_pin(self) -> bool:
        return (
            self._stream.isatty()
            and os.environ.get("TERM") != "dumb"
            and threading.current_thread() is threading.main_thread()
        )

    def _try_fetch_size(self) -> tuple[int, int] | None:
        try:
            size = os.get_terminal_size(self._stream.fileno())
        except (OSError, ValueError):
            return None
        if size.lines < _MIN_ROWS:
            return None
        return size.columns, size.lines

    def _calc_region(self) -> str:
        return f"{_CSI}1;{self._rows - 1}r"

    def _calc_clear(self) -> str:
        return f"{_CSI}{self._rows};1H{_CSI}2K"

    def _calc_draw(self) -> str:
        return f"{self._calc_clear()}{self._text[: self._cols - 1]}"

    def _write(self, text: str) -> None:
        with contextlib.suppress(OSError, ValueError):
            self._stream.write(text)
            self._stream.flush()

    def _on_resize(self, signum: int, frame: FrameType | None) -> None:
        size = self._try_fetch_size()
        if size is None:
            return
        cleared = self._calc_clear()
        self._cols, self._rows = size
        self._write(
            f"{_SAVE_CURSOR}{cleared}{self._calc_region()}{self._calc_draw()}{_RESTORE_CURSOR}"
        )

    def _on_kill(self, signum: int, frame: FrameType | None) -> None:
        self.disable()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
