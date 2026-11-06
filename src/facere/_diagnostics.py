"""Facere's own errors, printed in the GNU `file:line:column: severity: message` format."""

import contextlib
import inspect
import os
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from facere._context import Location

if TYPE_CHECKING:
    from typing_extensions import override
else:
    _F = TypeVar("_F", bound=Callable[..., object])

    def override(method: _F) -> _F:
        """Stand in for `typing.override`, which Python 3.11 lacks and which only marks the method."""
        return method


@dataclass(frozen=True, slots=True)
class Note:
    location: Location | None
    text: str


@dataclass(frozen=True, slots=True)
class Diagnostic:
    location: Location | None
    message: str
    notes: tuple[Note, ...] = ()


class FacereError(Exception):
    """An error Facere reports itself, whose diagnostics name the fac.py line involved where there is one, printed after `detail`, such as a traceback."""

    def __init__(self, *diagnostics: Diagnostic, detail: str = "") -> None:
        super().__init__(*diagnostics)
        self.diagnostics = diagnostics
        self.detail = detail

    @override
    def __str__(self) -> str:
        return "\n".join(_format_error(self, os.getcwd()))


def _format_error(error: FacereError, start_dir: str) -> list[str]:
    lines = [error.detail.rstrip("\n")] if error.detail else []
    for diagnostic in error.diagnostics:
        lines.append(
            f"{_format_location(diagnostic.location, start_dir)}: error: {diagnostic.message}"
        )
        lines.extend(
            f"{_format_location(note.location, start_dir)}: note: {note.text}"
            for note in diagnostic.notes
        )
    return lines


def print_error(error: FacereError, start_dir: str) -> None:
    for line in _format_error(error, start_dir):
        print(line, file=sys.stderr)


def _format_location(location: Location | None, start_dir: str) -> str:
    if location is None:
        return "fac"
    return f"{format_path(location.path, start_dir)}:{location.line}:{location.column}"


def format_path(path: str, start_dir: str) -> str:
    """Return `path` relative to `start_dir` where a relative path exists, with `/` on every OS."""
    with contextlib.suppress(ValueError):
        path = os.path.relpath(path, start_dir)
    return path.replace(os.sep, "/")


def find_caller_locations(fac_py: str | None) -> tuple[Location, Location]:
    """Return where the innermost frame executing `fac_py` stands, else the caller of Facere's public function, paired with where that caller stands."""
    package_dir = os.path.dirname(__file__)
    frame = sys._getframe(1)
    caller = None
    while frame is not None:
        if caller is None and os.path.dirname(frame.f_code.co_filename) != package_dir:
            caller = frame
        if frame.f_code.co_filename == fac_py:
            break
        frame = frame.f_back
    assert caller is not None
    return _to_location(frame or caller), _to_location(caller)


def _to_location(frame: types.FrameType) -> Location:
    info = inspect.getframeinfo(frame, context=0)
    column = (
        info.positions.col_offset if info.positions and info.positions.col_offset is not None else 0
    )
    return Location(info.filename, info.lineno, column + 1)
