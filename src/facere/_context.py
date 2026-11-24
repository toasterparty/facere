"""What one invocation of fac shares between collection, recipes, and Facere's public functions."""

import contextlib
import enum
import os
import posixpath
import sys
import threading
from collections.abc import Callable, Container, Generator, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from facere._command import Commands
    from facere._observed import Observed
    from facere._output import Output

STATE_DIR_NAME = ".fac"
STATE_FILE_NAME = "state.db"


class Kind(enum.Enum):
    INPUT = enum.auto()
    OUTPUT = enum.auto()
    ORDER_ONLY = enum.auto()
    ARGS = enum.auto()


class Console(enum.Enum):
    """How a command `fac.run` runs meets the terminal, given as `fac.run(..., console=fac.Console.LIVE)`.

    `LIVE` shares Facere's standard input, output, and error, so the command prints as it runs and may prompt. It is a task's default. In a rule, one such command runs at a time, holding the terminal while other rules' output waits, and it fails at once where Facere's standard input or error is no terminal. `AFTER` captures the output and prints it once the rule finishes, and is a rule's default unless `fac.console` sets another. `ON_FAILURE` captures the output and prints it only where the command's failure fails the recipe, and `fac -q` runs every command not running `LIVE` this way. A captured command reads an empty stdin unless `stdin=` names a file, and has no terminal to prompt on. In both captured modes a failing command's output travels in the raised error, so a failure the recipe catches prints nothing.
    """

    LIVE = enum.auto()
    AFTER = enum.auto()
    ON_FAILURE = enum.auto()


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
    is_always: bool
    pool: object
    rows: tuple[object, ...] | None
    values: dict[str, object]
    location: Location
    origin: Location


class UndeclaredUse(NamedTuple):
    path: str
    reason: str


class Pool:
    """A cap on how many of the rules given it execute at once, compared by identity."""

    __slots__ = ("size",)

    def __init__(self, size: int) -> None:
        self.size = size


@dataclass(slots=True)
class Recipe:
    """One executing recipe, with what the undeclared-path check and fac.add_inputs track of it.

    A task's commands and prints share Facere's own streams. A rule's are captured in `output`, in the order written, each chunk for stderr or else stdout, but for a command running `LIVE` and for everything after a `breakpoint()`, which sets `terminal_hold` to hold the terminal until the recipe ends, so the rest of its output shares Facere's streams as a task's does. Every path is keyed by calc_path_key, but `reported`, which keeps each reported path as normalize returns it, so two files differing only in case stay apart where the file system tells them apart. `tracked` holds the rule's inputs and outputs, `exempt` what its `str` parameters hold, and `output_keys` every output in the project. A recipe may open a shared module, but no command may name one, since what a command reads joins a fingerprint only as a declared input. `reported_names` holds the file name of every path reported outside `tracked`, dropped ones included. `undeclared`, the first use the check rejected, fails the rule however the recipe treats the error, as does `misuse`, the first call a thread the recipe started made that only the recipe's own thread may.
    """

    is_task: bool
    tracked: frozenset[str]
    order_only: frozenset[str]
    exempt: frozenset[str]
    shared_modules: frozenset[str]
    output_keys: Container[str]
    reported: set[str] = field(default_factory=set)
    reported_keys: set[str] = field(default_factory=set)
    reported_names: set[str] = field(default_factory=set)
    written: set[str] = field(default_factory=set)
    undeclared: UndeclaredUse | None = None
    misuse: str | None = None
    output: list[tuple[bool, bytes | str]] = field(default_factory=list)
    terminal_hold: contextlib.ExitStack | None = None

    @property
    def shares_streams(self) -> bool:
        return self.is_task or self.terminal_hold is not None


class _Threads(threading.local):
    """The recipe each thread executes, so rules executing at once never read one another's."""

    recipe: Recipe | None = None


@dataclass(slots=True)
class Context:
    """What one invocation shares.

    `is_loading` holds while a fac.py loads. `epoch` is what fac.epoch set, called at `epoch_location`, else 0 and None. `task` is the task executing, which executes alone, so any thread without a recipe of its own acts for it. `console` is the default fac.console set for rules' commands, called at `console_location`, else AFTER and None. `has_terminal` says whether Facere's stdin and stderr are both terminals, so a rule's command may run `LIVE`. `window_size` is the terminal's rows and columns where Facere's stderr is a terminal a rule's command may be given one like, else None. `output` is Facere's own streams while a build runs. `give_lock_cb` gives the output directory's lock on a task's request. `observed` gathers what the invocation observed where it is a cycle of a watch, else None.
    """

    root: str
    out_dir: str
    fac_py: str
    is_quiet: bool
    is_verbose: bool
    has_terminal: bool
    commands: "Commands"
    declarations: list[Declaration] = field(default_factory=list)
    env: dict[str, str | None] = field(default_factory=dict)
    env_locations: dict[str, Location] = field(default_factory=dict)
    epoch: int = 0
    epoch_location: Location | None = None
    console: Console = Console.AFTER
    console_location: Location | None = None
    is_loading: bool = False
    task: Recipe | None = None
    window_size: tuple[int, int] | None = None
    output: "Output | None" = None
    give_lock_cb: Callable[[], None] | None = None
    observed: "Observed | None" = None
    _threads: _Threads = field(default_factory=_Threads)
    _starters_lock: threading.Lock = field(default_factory=threading.Lock)
    # Each thread a rule's recipe started, until that recipe ends, and each rule's recipe executing.
    _starters: dict[threading.Thread, Recipe] = field(default_factory=dict)
    _executing: list[Recipe] = field(default_factory=list)

    @property
    def state_dir(self) -> str:
        return posixpath.normpath(posixpath.join(self.out_dir, STATE_DIR_NAME))

    def find_rule_recipe(self) -> Recipe | None:
        """Return the rule's recipe the calling thread executes, or None."""
        return self._threads.recipe

    def find_recipe(self) -> Recipe | None:
        """Return the recipe the calling thread acts for: its own, or else the executing task's."""
        return self._threads.recipe or self.task

    def find_starters(self) -> list[Recipe]:
        """Return the rule's recipe that started the calling thread, itself or through a thread it started. Before Python 3.12, which tells no thread's start, return every rule's recipe executing, since any of them may have."""
        with self._starters_lock:
            if sys.version_info < (3, 12):
                return list(self._executing)
            starter = self._starters.get(threading.current_thread())
            return [] if starter is None else [starter]

    def note_started(self, thread: threading.Thread) -> None:
        """Remember that the calling thread starts `thread`, where it executes a rule's recipe or such a recipe started it."""
        recipe = self._threads.recipe
        with self._starters_lock:
            recipe = recipe or self._starters.get(threading.current_thread())
            if recipe is not None:
                self._starters[thread] = recipe

    @contextlib.contextmanager
    def executing(self, recipe: Recipe) -> Generator[None]:
        """Execute `recipe` on the calling thread for the length of the block."""
        if recipe.is_task:
            self.task = recipe
        else:
            self._threads.recipe = recipe
            with self._starters_lock:
                self._executing.append(recipe)
        try:
            yield
        finally:
            if recipe.terminal_hold is not None:
                recipe.terminal_hold.close()
            self.task = None
            self._threads.recipe = None
            with self._starters_lock:
                for thread in [key for key, value in self._starters.items() if value is recipe]:
                    del self._starters[thread]
                self._executing[:] = [other for other in self._executing if other is not recipe]

    def forget_collection(self) -> None:
        """Drop what loading the fac.py declared, before loading it again."""
        self.declarations.clear()
        self.env.clear()
        self.env_locations.clear()
        self.epoch = 0
        self.epoch_location = None
        self.console = Console.AFTER
        self.console_location = None


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


def holds_state(directory: str) -> bool:
    """Say whether `directory` holds Facere's state, as each output directory a build used does."""
    return os.path.isfile(os.path.join(directory, STATE_DIR_NAME, STATE_FILE_NAME))


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
