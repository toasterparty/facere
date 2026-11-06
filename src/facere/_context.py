"""What one invocation of fac shares between collection, recipes, and Facere's public functions."""

import contextlib
import enum
import os
import posixpath
from collections.abc import Callable, Generator
from dataclasses import dataclass, field


class Kind(enum.Enum):
    INPUT = enum.auto()
    OUTPUT = enum.auto()
    ARGS = enum.auto()


class Running(enum.Enum):
    RULE = enum.auto()
    TASK = enum.auto()


@dataclass(frozen=True, slots=True)
class Location:
    path: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class Declaration:
    """One application of @fac.rule or @fac.task, as the decorator received it.

    `location` is the innermost line of the root's fac.py that led to it, and `origin` the decorator's own line, which differs when a module declared it.
    """

    is_task: bool
    fn: Callable[..., object]
    name: str | None
    is_default: bool
    rows: tuple[object, ...] | None
    values: dict[str, object]
    location: Location
    origin: Location


@dataclass(slots=True)
class Context:
    root: str
    out_dir: str
    fac_py: str
    is_quiet: bool
    is_verbose: bool
    declarations: list[Declaration] = field(default_factory=list)
    env: dict[str, str | None] = field(default_factory=dict)
    env_locations: dict[str, Location] = field(default_factory=dict)
    running: Running | None = None

    @property
    def state_dir(self) -> str:
        return posixpath.normpath(posixpath.join(self.out_dir, ".fac"))


_current: Context | None = None


def find_context() -> Context | None:
    return _current


def get_context(caller: str) -> Context:
    if _current is None:
        raise RuntimeError(f"{caller} works only while fac runs a fac.py")
    return _current


@contextlib.contextmanager
def activate(context: Context) -> Generator[None]:
    global _current
    previous = _current
    _current = context
    try:
        yield
    finally:
        _current = previous


def is_under_root(path: str, root: str) -> bool:
    """Say whether the filesystem path `path` lies inside `root`, compared lexically, without resolving links or case."""
    return os.path.abspath(path).startswith(os.path.join(root, ""))


def is_within(path: str, directory: str) -> bool:
    """Say whether `path` is `directory` or lies inside it, both as normalize returns them."""
    return directory == "." or path == directory or path.startswith(f"{directory}/")


def normalize(path: str, root: str) -> str:
    """Return `path` relative to `root` with `/`, or absolute where no relative path exists."""
    if not isinstance(path, str):
        raise TypeError(f"Facere paths are strings with /, not {type(path).__name__}")
    if not path:
        raise ValueError("a path is empty")
    if os.path.isabs(path):
        with contextlib.suppress(ValueError):
            path = os.path.relpath(path, root)
    return posixpath.normpath(path.replace(os.sep, "/"))
