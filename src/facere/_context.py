"""What one invocation of fac shares between collection, recipes, and Facere's public functions."""

import contextlib
import enum
import os
import posixpath
from collections.abc import Callable, Container, Generator, Iterator
from dataclasses import dataclass, field
from typing import NamedTuple


class Kind(enum.Enum):
    INPUT = enum.auto()
    OUTPUT = enum.auto()
    ORDER_ONLY = enum.auto()
    ARGS = enum.auto()


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


class UndeclaredUse(NamedTuple):
    path: str
    reason: str


@dataclass(slots=True)
class Recipe:
    """The recipe executing now, with what the undeclared-path check and fac.add_inputs track of it.

    Every collection of paths is keyed by calc_path_key. `tracked` holds its rule's inputs and outputs, `exempt` the paths its `str` parameters hold, `shared_modules` what a recipe may open but no command may name, since a recipe's reach decides whether a fingerprint holds one, and `output_keys` every output in the project. `reported` maps the key of each path fac.add_inputs kept to that path, `reported_names` holds the file name of every path it was given outside `tracked`, those it dropped included, and `undeclared` the first use the undeclared-path check rejected, which fails the rule however the recipe treats the error.
    """

    is_task: bool
    thread_id: int
    tracked: frozenset[str]
    order_only: frozenset[str]
    exempt: frozenset[str]
    shared_modules: frozenset[str]
    output_keys: Container[str]
    reported: dict[str, str] = field(default_factory=dict)
    reported_names: set[str] = field(default_factory=set)
    written: set[str] = field(default_factory=set)
    undeclared: UndeclaredUse | None = None


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
    running: Recipe | None = None

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


def calc_path_key(path: str) -> str:
    """Return what `path` compares by, without case, so Facere decides alike on every OS."""
    return path.casefold()


def iter_self_and_parents(path: str) -> Iterator[str]:
    """Yield `path`, as normalize returns it, then each directory holding it."""
    while path:
        yield path
        parent = posixpath.dirname(path)
        if parent == path:
            return
        path = parent


def is_within_any(key: str, directories: Container[str]) -> bool:
    """Say whether the path key `key` is one of `directories`, or lies inside one."""
    return any(path in directories for path in iter_self_and_parents(key))


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
