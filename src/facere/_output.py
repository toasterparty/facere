"""What an invocation writes to its own streams while it builds: each rule's output whole, never mixed with another's."""

import contextlib
import sys
import threading
from collections.abc import Callable, Generator, Iterable
from typing import TextIO, cast

from facere._context import Context

Chunk = tuple[bool, bytes | str]
"""A piece of output, for stderr or else stdout: bytes a command wrote, written unaltered, or text."""


class Output:
    """Facere's own streams, written by one thread at a time.

    While the terminal is held, for a rule that prompts, everything else waits, and is written once it is given back.
    """

    def __init__(self, stdout: TextIO, stderr: TextIO, status_cb: Callable[[str], None]) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._status_cb = status_cb
        self._lock = threading.Lock()
        self._is_held = False
        self._waiting: list[Chunk] = []

    def write(self, chunks: Iterable[Chunk]) -> None:
        """Write `chunks` in order with nothing between them."""
        with self._lock:
            if self._is_held:
                self._waiting.extend(chunks)
            else:
                self._write(chunks)

    def print(self, *lines: str) -> None:
        """Write `lines`, each a line of Facere's own, to stderr."""
        self.write([(True, "".join(f"{line}\n" for line in lines))])

    def show_status(self, text: str) -> None:
        """Show `text` on the status row, unless the terminal is held."""
        with self._lock:
            if not self._is_held:
                self._status_cb(text)

    def take_terminal(self) -> None:
        with self._lock:
            self._is_held = True

    def give_terminal(self) -> None:
        with self._lock:
            self._is_held = False
            waiting, self._waiting = self._waiting, []
            self._write(waiting)

    def _write(self, chunks: Iterable[Chunk]) -> None:
        for is_stderr, data in chunks:
            if data:
                write_data(self._stderr if is_stderr else self._stdout, data)


def write_data(stream: TextIO, data: bytes | str) -> None:
    """Write `data` to `stream` and flush it, bytes unaltered where the stream has a binary layer."""
    if isinstance(data, bytes):
        stream.flush()
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            buffer.write(data)
            buffer.flush()
            return
        data = data.decode("utf-8", "replace")
    stream.write(data)
    stream.flush()


@contextlib.contextmanager
def capture_recipes(context: Context) -> Generator[tuple[TextIO, TextIO]]:
    """Keep what each rule's recipe writes to `sys.stdout` and `sys.stderr` from its own thread in that recipe's output, for the length of the block, and yield the two streams as they were.

    A task's writes, and those of a rule that has the terminal, pass through, as do those of any thread a recipe started.
    """
    stdout = cast("TextIO", sys.stdout)
    stderr = cast("TextIO", sys.stderr)
    sys.stdout = cast("TextIO", _RecipeText(stdout, False, context))
    sys.stderr = cast("TextIO", _RecipeText(stderr, True, context))
    try:
        yield stdout, stderr
    finally:
        sys.stdout, sys.stderr = stdout, stderr


class _RecipeBytes:
    """Stands in for a standard stream's binary layer."""

    def __init__(self, stream: TextIO, is_stderr: bool, context: Context) -> None:
        self._stream = stream
        self._is_stderr = is_stderr
        self._context = context

    def write(self, data: bytes) -> int:
        recipe = self._context.find_rule_recipe()
        if recipe is None or recipe.has_terminal:
            self._stream.flush()
            return self._stream.buffer.write(data)
        recipe.output.append((self._is_stderr, bytes(data)))
        return len(data)

    def flush(self) -> None:
        self._stream.buffer.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream.buffer, name)


class _RecipeText:
    """Stands in for `sys.stdout` or `sys.stderr`."""

    def __init__(self, stream: TextIO, is_stderr: bool, context: Context) -> None:
        self._stream = stream
        self._is_stderr = is_stderr
        self._context = context
        if hasattr(stream, "buffer"):
            self.buffer = _RecipeBytes(stream, is_stderr, context)

    def write(self, text: str) -> int:
        recipe = self._context.find_rule_recipe()
        if recipe is None or recipe.has_terminal:
            return self._stream.write(text)
        recipe.output.append((self._is_stderr, text))
        return len(text)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)
