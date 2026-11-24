"""The decorators and helpers a fac.py calls to define rules and tasks."""

import abc
import errno
import glob
import os
import posixpath
from collections.abc import Callable, Collection, Iterable, Mapping
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, Protocol, TypeVar, overload

from facere._context import (
    Console,
    Context,
    Declaration,
    Kind,
    Pool,
    Recipe,
    calc_path_key,
    find_context,
    get_context,
    holds_state,
    is_under_root,
    is_within,
    is_within_any,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note, find_caller_locations, override
from facere._hash import UnhashableValueError, calc_value_digest
from facere._undeclared import note_misuse
from facere._version import VERSION

if TYPE_CHECKING:
    import typing_extensions

    # A default, which typing.TypeVar gains only in Python 3.13, makes bare fac.Input mean str.
    _Target = typing_extensions.TypeVar("_Target", default=str)
else:
    _Target = TypeVar("_Target")

_K = TypeVar("_K")
_V = TypeVar("_V")

Input = Annotated[_Target, Kind.INPUT]
"""Annotates a parameter holding a file or directory the rule or task reads, as a path relative to the root. Use `list[fac.Input]` for several, and `fac.Input[fac.Virtual]` for a rule's parameter holding a virtual output another rule writes, or a virtual source."""
OrderOnly = Annotated[str, Kind.ORDER_ONLY]
"""Annotates a rule's parameter holding a file or directory its recipe may read, as a path relative to the root. It is built first, and its path joins the fingerprint, but a change to its content makes the rule stale only once the recipe reports reading it through `fac.add_inputs`. Use `list[fac.OrderOnly]` for several."""
Output = Annotated[_Target, Kind.OUTPUT]
"""Annotates a parameter holding a file or directory the rule writes, as a path relative to the root. Use `list[fac.Output]` for several, and `fac.Output[fac.Virtual]` for a virtual output the recipe sets through `fac.write`."""
Args = Annotated[tuple[str, ...], Kind.ARGS]
"""Annotates a task's parameter holding the arguments after `--` on the command line."""

_F = TypeVar("_F", bound=Callable[..., object])


class Store(Protocol[_K, _V]):
    """What a store class provides, for type checking only, so a store need not subclass it.

    `stamp()` returns a token Facere can hash that changes whenever any virtual output does, or None where the store has none. `read(keys)` returns the virtual outputs among `keys` the store holds, and may return others. `update(changed)` writes the virtual outputs given and leaves the rest as they were. Facere calls one store's methods one at a time, with the root as working directory, and fails the invocation where one changes an attribute of the store.
    """

    def stamp(self) -> object: ...

    def read(self, keys: Collection[_K], /) -> Mapping[_K, _V]: ...

    def update(self, changed: Mapping[_K, _V], /) -> None: ...


class FileStore(abc.ABC):
    """A store kept in the one file at `path`, relative to the root, which identifies it.

    A subclass implements `read()`, returning every virtual output the file holds as a dict from key to value, and `write(outputs)`, replacing the file with exactly the virtual outputs given. Facere never calls `read` while the file is missing, counts a file whose `read` raises before Facere first writes to it as holding nothing, and stamps it by the file's hash, which the hash cache vouches for with one stat. An update reads the file, replaces the virtual outputs that changed, and passes `write` every virtual output, first those the rules declare in definition order, then the rest in the order `read` returned them.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    @abc.abstractmethod
    def read(self) -> Mapping[Any, Any]: ...

    @abc.abstractmethod
    def write(self, outputs: Mapping[Any, Any], /) -> None: ...


class Virtual:
    """One virtual output, `key` in `store`, or a virtual source, `key` whose content `fingerprint(key)` signs. Exactly one of `store=` and `fingerprint=` is given.

    A virtual output is a value, so it goes in `each=` rows, values, and module constants, and two compare equal when their keys are equal and they name the same store object or signature function. A rule declares one with `fac.Output[fac.Virtual]` to write it, or `fac.Input[fac.Virtual]` to read it.
    """

    __slots__ = ("fingerprint", "key", "store")

    def __init__(
        self,
        key: object,
        *,
        store: Store[Any, Any] | FileStore | None = None,
        fingerprint: Callable[[Any], object] | None = None,
    ) -> None:
        if (store is None) == (fingerprint is None):
            raise TypeError("fac.Virtual takes exactly one of store= and fingerprint=")
        self.key = key
        self.store = store
        self.fingerprint = fingerprint

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Virtual):
            return NotImplemented
        return (
            self.key == other.key
            and self.store is other.store
            and self.fingerprint is other.fingerprint
        )

    @override
    def __hash__(self) -> int:
        return hash((self.key, id(self.store), self.fingerprint))

    @override
    def __repr__(self) -> str:
        if self.store is None:
            assert self.fingerprint is not None
            source = f"fingerprint={getattr(self.fingerprint, '__qualname__', self.fingerprint)}"
        else:
            source = f"store={type(self.store).__qualname__}"
        return f"fac.Virtual({self.key!r}, {source})"


@overload
def rule(fn: _F, /) -> _F: ...


@overload
def rule(
    *,
    each: Iterable[dict[str, Any]] | None = None,
    name: str | None = None,
    default: bool = False,
    always: bool = False,
    pool: Pool | None = None,
    **values: object,
) -> Callable[[_F], _F]: ...


def rule(
    fn: _F | None = None,
    /,
    *,
    each: Iterable[dict[str, Any]] | None = None,
    name: str | None = None,
    default: bool = False,
    always: bool = False,
    pool: Pool | None = None,
    **values: object,
) -> _F | Callable[[_F], _F]:
    """Define rules from a function, returned unchanged.

    The function's signature declares what each rule reads and writes: a parameter annotated `fac.Input` or `list[fac.Input]` holds the files or directories it reads, one annotated `fac.OrderOnly` or `list[fac.OrderOnly]` those it may read, one annotated `fac.Output` or `list[fac.Output]` files or directories it writes, one annotated `fac.Input[fac.Virtual]` or `fac.Output[fac.Virtual]`, alone or in a list, virtual outputs it reads or writes, the first also virtual sources, and any other parameter a value. `each=` takes an iterable of dicts, read once here, and defines one rule per dict, each key filling the parameter it names. Keyword arguments fill the parameters they name in every rule, and defaults fill the rest. `name=` replaces the function's name, less one trailing underscore, on the command line, and `default=True` builds the rules when `fac` gets no targets, in place of every rule. `always=True` executes the rules whenever a target reaches them, for what Facere can't see change, such as a program's version, while the rules downstream execute only when an output's content changed. `pool=` takes what `fac.pool` returned, and caps how many of the rules given that pool execute at once.
    """
    rows = None if each is None else tuple(each)
    return _declarator(
        fn,
        is_task=False,
        name=name,
        is_default=default,
        is_always=always,
        pool=pool,
        rows=rows,
        values=values,
    )


@overload
def task(fn: _F, /) -> _F: ...


@overload
def task(
    *, name: str | None = None, default: bool = False, **values: object
) -> Callable[[_F], _F]: ...


def task(
    fn: _F | None = None, /, *, name: str | None = None, default: bool = False, **values: object
) -> _F | Callable[[_F], _F]:
    """Define a task from a function, returned unchanged.

    A task takes inputs and values only, and executes whenever a target reaches it, alone, after the rules that output its inputs, with its commands running `fac.Console.LIVE` by default. A parameter annotated `fac.Args` holds the arguments after `--` on the command line when the task is among the targets, else its default, else `()`. `name=`, `default=True`, and keyword arguments mean what they mean for `fac.rule`.
    """
    return _declarator(
        fn,
        is_task=True,
        name=name,
        is_default=default,
        is_always=False,
        pool=None,
        rows=None,
        values=values,
    )


def out(path: str = ".", suffix: str | None = None) -> str:
    """Return the mirror of `path` inside the output directory, with its suffix swapped for `suffix` when given.

    `fac.out("src/a.c", ".o")` is `build/src/a.o`, and `fac.out()` is the output directory itself. A path already inside the output directory keeps its place.
    """
    context = get_context("fac.out")
    relative = normalize(path, context.root)
    if is_within(relative, context.out_dir):
        mirrored = relative
    elif os.path.isabs(relative) or relative == ".." or relative.startswith("../"):
        raise ValueError(f"fac.out takes a path under the root, not {path!r}")
    else:
        mirrored = posixpath.normpath(posixpath.join(context.out_dir, relative))
    if suffix is None:
        return mirrored
    return PurePosixPath(mirrored).with_suffix(suffix).as_posix()


def pool(size: int) -> Pool:
    """Return a pool that lets `size` of the rules given it execute at once, as in `LINKS = fac.pool(2)` and `@fac.rule(pool=LINKS)`, for rules that are bound by memory or that run workers of their own."""
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError(f"fac.pool takes how many rules may execute at once, not {size!r}")
    return Pool(size)


def give_lock() -> None:
    """Let other invocations use the output directory while the calling task goes on, as a server that keeps running does.

    Facere first saves its state and checks that every output this invocation built is still as its rule left it. From then on, another invocation may rebuild a file the task is using. Facere takes the lock again before the targets after the task. A second call does nothing, and a rule's recipe that calls it fails, since recording a rule needs the lock.
    """
    context = get_context("fac.give_lock")
    recipe = context.find_recipe()
    if recipe is None or not recipe.is_task or context.give_lock_cb is None:
        raise RuntimeError(
            "fac.give_lock works only in the recipe of a task, since recording a rule needs the lock"
        )
    context.give_lock_cb()


def add_inputs(paths: Iterable[str]) -> None:
    """Report files the running rule's recipe read, usually what a tool's depfile lists, so a change to any of them makes the rule stale.

    Call it once its tool has run or before reading a file in Python. Each path is relative to the root, or absolute, and any spelling of one counts, such as `src/a/../b.h`. A new file under the root with the name of a reported file makes the rule stale. A file inside the output directory that no rule outputs is scratch, so only its name is kept. A file reported for the first time that changed since the invocation's first rule started executing, or since the rule outputting it finished, leaves the rule stale. Raises IsADirectoryError for a directory, and FileNotFoundError for a kept path that doesn't exist.
    """
    context = get_context("fac.add_inputs")
    recipe = context.find_rule_recipe()
    if recipe is None:
        note_misuse(context, "fac.add_inputs")
        raise RuntimeError(
            "fac.add_inputs reports inputs only from the recipe of a rule, on the recipe's own thread, since a task records nothing"
        )
    if isinstance(paths, str):
        raise TypeError(f"fac.add_inputs takes a list of paths, not the string {paths!r}")
    for path in paths:
        relative = normalize(path, context.root)
        key = calc_path_key(relative)
        if is_within_any(key, recipe.tracked):
            continue
        if os.path.isdir(os.path.join(context.root, relative)):
            raise IsADirectoryError(
                errno.EISDIR,
                "fac.add_inputs takes files, and a directory a rule reads is a fac.Input",
                relative,
            )
        recipe.reported_names.add(calc_path_key(posixpath.basename(relative)))
        if is_within(relative, context.out_dir) and not is_within_any(key, recipe.output_keys):
            continue
        if not os.path.exists(os.path.join(context.root, relative)):
            raise FileNotFoundError(errno.ENOENT, "fac.add_inputs got a missing file", relative)
        recipe.reported.add(relative)
        recipe.reported_keys.add(key)


def write(output: Virtual, value: object) -> None:
    """Set `output`, a virtual output the running rule's recipe declares, to `value`, replacing what an earlier call set. Facere writes it to its store once the batch of rules ends.

    Raises TypeError for a value Facere can't hash, and ValueError for a virtual output the rule doesn't declare.
    """
    context = get_context("fac.write")
    recipe = _get_rule_recipe(context, "fac.write")
    key = recipe.virtual_outputs.get(_validate_virtual("fac.write", output))
    if key is None:
        raise ValueError(
            f"fac.write got {output!r}, which the rule declares as no fac.Output[fac.Virtual]"
        )
    try:
        digest = calc_value_digest(value)
    except UnhashableValueError as error:
        raise TypeError(
            f"fac.write got a value of type {error.type_name}, which Facere can't hash, since {error.reason}"
        ) from None
    recipe.values[key] = (value, digest)


def read(virtual_input: Virtual) -> Any:  # noqa: ANN401 - a fac.Virtual carries no value type
    """Return the value of `virtual_input`, a virtual output the running rule's recipe declares as an input: as a rule wrote it earlier in the invocation, as its store returned it earlier, or else as its store's `read` returns it now.

    Raises ValueError for a virtual source, whose content Facere knows only by its signature, and for a virtual output the rule doesn't declare.
    """
    context = get_context("fac.read")
    recipe = _get_rule_recipe(context, "fac.read")
    if _validate_virtual("fac.read", virtual_input).store is None:
        raise ValueError(
            f"fac.read got the virtual source {virtual_input!r}, whose content Facere knows only by its signature"
        )
    key = recipe.virtual_inputs.get(virtual_input)
    if key is None:
        raise ValueError(
            f"fac.read got {virtual_input!r}, which the rule declares as no fac.Input[fac.Virtual]"
        )
    assert recipe.read_virtual_cb is not None
    return recipe.read_virtual_cb(key)


def _get_rule_recipe(context: Context, caller: str) -> Recipe:
    recipe = context.find_rule_recipe()
    if recipe is None:
        note_misuse(context, caller)
        raise RuntimeError(
            f"{caller} works only in the recipe of a rule, on the recipe's own thread, since a task records nothing"
        )
    return recipe


def _validate_virtual(caller: str, virtual: object) -> Virtual:
    if not isinstance(virtual, Virtual):
        raise TypeError(f"{caller} takes a fac.Virtual, not {virtual!r}")
    return virtual


def read_text(path: str) -> str:
    """Return the text of the UTF-8 file at `path`, relative to the root, with every line ending read as `\\n`."""
    with open(path, encoding="utf-8") as file:
        return file.read()


def write_text(path: str, text: str) -> None:
    """Replace the file at `path`, relative to the root, with `text` in UTF-8, ending lines with `\\n` on every OS so the bytes match across machines."""
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)


def env(**variables: str | None) -> None:
    """Set each variable for every command this invocation runs, or unset it when `None`, and join them all to every rule's fingerprint.

    Call it while fac.py loads, as in `fac.env(LC_ALL="C", CPATH=None)`. Calls may repeat a variable's value but never change it, and `env=` to `fac.run` overrides them for one command.
    """
    context = _get_loading_context("fac.env")
    location, _ = find_caller_locations(context.fac_py)
    for name, value in variables.items():
        if value is not None and not isinstance(value, str):
            raise TypeError(
                f"fac.env sets {name} to a string, or unsets it with None, not {value!r}"
            )
        if name in context.env and context.env[name] != value:
            earlier = context.env_locations[name]
            raise FacereError(
                Diagnostic(
                    location,
                    f"fac.env sets {name} to {value!r}, though another call set it to {context.env[name]!r}",
                    (Note(earlier, f"fac.env sets {name} here"),),
                )
            )
    for name, value in variables.items():
        context.env[name] = value
        context.env_locations.setdefault(name, location)


def epoch(number: int) -> None:
    """Join `number`, a whole number from 0, to every rule's fingerprint, so raising it executes every rule once, on every machine that builds the commit.

    Call it while the root's fac.py loads, as in `fac.epoch(1)`, and raise it where an edit to code a recipe calls, such as a helper, a class, or a shared module, which no fingerprint holds, changes what rules build. Without a call the epoch is 0. Calls may repeat the number but never change it.
    """
    context = _get_loading_context("fac.epoch")
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
        raise ValueError(f"fac.epoch takes a whole number from 0, not {number!r}")
    location, _ = find_caller_locations(context.fac_py)
    earlier = context.epoch_location
    if earlier is not None and context.epoch != number:
        raise FacereError(
            Diagnostic(
                location,
                f"fac.epoch sets {number}, though another call set {context.epoch}",
                (Note(earlier, "fac.epoch sets the epoch here"),),
            )
        )
    context.epoch = number
    context.epoch_location = earlier or location


def console(mode: Console) -> None:
    """Make `mode`, a fac.Console member, the default for the commands of every rule, as in `fac.console(fac.Console.ON_FAILURE)` for a project whose tools print only noise when they succeed.

    Call it while fac.py loads. An explicit `console=` to `fac.run` overrides it, and a task's commands keep `LIVE`. Calls may repeat the mode but never change it.
    """
    context = _get_loading_context("fac.console")
    if not isinstance(mode, Console):
        raise TypeError(f"fac.console takes a fac.Console member, not {mode!r}")
    location, _ = find_caller_locations(context.fac_py)
    earlier = context.console_location
    if earlier is not None and context.console is not mode:
        raise FacereError(
            Diagnostic(
                location,
                f"fac.console sets {mode.name}, though another call set {context.console.name}",
                (Note(earlier, "fac.console sets the default here"),),
            )
        )
    context.console = mode
    context.console_location = earlier or location


def sources(*patterns: str) -> list[str]:
    """Return the files under the root that match any of `patterns`, sorted, as paths relative to the root with `/`.

    Each pattern is a glob relative to the root, in which `**` matches any number of directories, as in `fac.sources("src/**/*.c")`. A file or directory whose name starts with `.` matches only a pattern part that starts with `.`, and nothing in the output directory, or in another directory holding Facere's state, matches. Call it while fac.py loads.
    """
    context = _get_loading_context("fac.sources")
    return sorted({path for pattern in patterns for path in _glob(context, pattern)})


def minimum_version(version: str) -> None:
    """Fail collection unless the running Facere is `version` or newer, as in `fac.minimum_version("0.1")`."""
    required = _parse_version(version)
    running = _parse_version(VERSION)
    width = max(len(required), len(running))
    if running + (0,) * (width - len(running)) >= required + (0,) * (width - len(required)):
        return
    shown_required, shown_running = _format_versions(required, running)
    context = find_context()
    location, _ = find_caller_locations(context.fac_py if context else None)
    raise FacereError(
        Diagnostic(
            location,
            f"this project needs Facere {shown_required} or newer. Detected {shown_running}: run `uv tool upgrade facere`",
        )
    )


def _get_loading_context(caller: str) -> Context:
    context = get_context(caller)
    if not context.is_loading:
        raise RuntimeError(
            f"{caller} works only while fac.py loads, since a recipe that calls it reads what no fingerprint holds"
        )
    return context


def _glob(context: Context, pattern: str) -> list[str]:
    if not isinstance(pattern, str) or not pattern:
        raise ValueError(f"fac.sources takes globs relative to the root, not {pattern!r}")
    relative = PurePosixPath(pattern)
    if relative.is_absolute() or os.path.isabs(pattern) or ".." in relative.parts:
        raise ValueError(f"fac.sources takes globs under the root, not {pattern!r}")
    paths = []
    is_state_by_directory: dict[str, bool] = {}
    for match in glob.glob(pattern, root_dir=context.root, recursive=True):
        path = normalize(match, context.root)
        absolute = os.path.join(context.root, path)
        is_listed = is_under_root(absolute, context.root) and not is_within(path, context.out_dir)
        if not is_listed or not os.path.isfile(absolute):
            continue
        if not _is_in_output_directory(context.root, path, is_state_by_directory):
            paths.append(path)
    return paths


def _is_in_output_directory(root: str, path: str, is_state_by_directory: dict[str, bool]) -> bool:
    """Say whether `path` lies in a directory holding Facere's state, as another `--out` leaves one, caching each directory's answer in `is_state_by_directory`."""
    for directory in iter_self_and_parents(posixpath.dirname(path)):
        if directory not in is_state_by_directory:
            is_state_by_directory[directory] = holds_state(os.path.join(root, directory))
        if is_state_by_directory[directory]:
            return True
    return False


def _parse_version(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if not all(part.isdecimal() for part in parts):
        raise ValueError(f'fac.minimum_version takes a version such as "0.1", not {version!r}')
    return tuple(int(part) for part in parts)


def _format_versions(required: tuple[int, ...], running: tuple[int, ...]) -> tuple[str, str]:
    """Return both versions as major.minor, unless only a later part tells them apart."""
    width = None if required[:2] == running[:2] else 2
    return ".".join(map(str, required[:width])), ".".join(map(str, running[:width]))


def _declarator(
    fn: _F | None,
    *,
    is_task: bool,
    name: str | None,
    is_default: bool,
    is_always: bool,
    pool: object,
    rows: tuple[object, ...] | None,
    values: dict[str, object],
) -> _F | Callable[[_F], _F]:
    def declare(fn: _F) -> _F:
        context = get_context("@fac.task" if is_task else "@fac.rule")
        location, origin = find_caller_locations(context.fac_py)
        context.declarations.append(
            Declaration(
                is_task=is_task,
                fn=fn,
                name=name,
                is_default=is_default,
                is_always=is_always,
                pool=pool,
                rows=rows,
                values=values,
                location=location,
                origin=origin,
            )
        )
        return fn

    return declare if fn is None else declare(fn)
