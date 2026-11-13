"""The decorators and helpers a fac.py calls to define rules and tasks."""

import errno
import glob
import os
import posixpath
from collections.abc import Callable, Iterable
from pathlib import PurePosixPath
from typing import Annotated, Any, TypeVar, overload

from facere._context import (
    STATE_DIR_NAME,
    STATE_FILE_NAME,
    Context,
    Declaration,
    Kind,
    calc_path_key,
    find_context,
    get_context,
    is_under_root,
    is_within,
    is_within_any,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note, find_caller_locations
from facere._version import VERSION

Input = Annotated[str, Kind.INPUT]
"""Annotates a parameter holding a file or directory the rule or task reads, as a path relative to the root. Use `list[fac.Input]` for several."""
OrderOnly = Annotated[str, Kind.ORDER_ONLY]
"""Annotates a rule's parameter holding a file or directory its recipe may read, as a path relative to the root. It is built first, and its path joins the fingerprint where the recipe's code names the parameter, but a change to its content makes the rule stale only once the recipe reports reading it through `fac.add_inputs`. Use `list[fac.OrderOnly]` for several."""
Output = Annotated[str, Kind.OUTPUT]
"""Annotates a parameter holding a file or directory the rule writes, as a path relative to the root. Use `list[fac.Output]` for several."""
Args = Annotated[tuple[str, ...], Kind.ARGS]
"""Annotates a task's parameter holding the arguments after `--` on the command line."""

_F = TypeVar("_F", bound=Callable[..., object])


@overload
def rule(fn: _F, /) -> _F: ...


@overload
def rule(
    *,
    each: Iterable[dict[str, Any]] | None = None,
    name: str | None = None,
    default: bool = False,
    always: bool = False,
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
    **values: object,
) -> _F | Callable[[_F], _F]:
    """Define rules from a function, returned unchanged.

    The function's signature declares what each rule reads and writes: a parameter annotated `fac.Input` or `list[fac.Input]` holds the files or directories it reads, one annotated `fac.OrderOnly` or `list[fac.OrderOnly]` those it may read, one annotated `fac.Output` or `list[fac.Output]` files or directories it writes, and any other parameter a value. `each=` takes an iterable of dicts, read once here, and defines one rule per dict, each key filling the parameter it names. Keyword arguments fill the parameters they name in every rule, and defaults fill the rest. `name=` replaces the function's name, less one trailing underscore, on the command line, and `default=True` builds the rules when `fac` gets no targets, in place of every rule. `always=True` executes the rules whenever a target reaches them, for what Facere can't see change, such as a program's version, while the rules downstream execute only when an output's content changed.
    """
    rows = None if each is None else tuple(each)
    return _declarator(
        fn,
        is_task=False,
        name=name,
        is_default=default,
        is_always=always,
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

    A task takes inputs and values only, and executes whenever a target reaches it, after the rules that output its inputs, with its commands sharing Facere's standard streams. A parameter annotated `fac.Args` holds the arguments after `--` on the command line when the task is among the targets, else its default, else `()`. `name=`, `default=True`, and keyword arguments mean what they mean for `fac.rule`.
    """
    return _declarator(
        fn, is_task=True, name=name, is_default=default, is_always=False, rows=None, values=values
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


def add_inputs(paths: Iterable[str]) -> None:
    """Report files the running rule's recipe read, usually what a tool's depfile lists, so a change to any of them makes the rule stale.

    Call it once its tool has run or before reading a file in Python. Each path is relative to the root, or absolute, and any spelling of one counts, such as `src/a/../b.h`. A new file under the root with the name of a reported file makes the rule stale. A file inside the output directory that no rule outputs is scratch, so only its name is kept. A file reported for the first time that changed since the invocation's first rule started executing, or since the rule outputting it finished, leaves the rule stale. Raises IsADirectoryError for a directory, and FileNotFoundError for a kept path that doesn't exist.
    """
    context = get_context("fac.add_inputs")
    recipe = context.running
    if recipe is None or recipe.is_task:
        raise RuntimeError(
            "fac.add_inputs reports inputs only from the recipe of a rule, since a task records nothing"
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
    if context.running is not None:
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
    holds_state: dict[str, bool] = {}
    for match in glob.glob(pattern, root_dir=context.root, recursive=True):
        path = normalize(match, context.root)
        absolute = os.path.join(context.root, path)
        is_listed = is_under_root(absolute, context.root) and not is_within(path, context.out_dir)
        if not is_listed or not os.path.isfile(absolute):
            continue
        if not _is_in_output_directory(context.root, path, holds_state):
            paths.append(path)
    return paths


def _is_in_output_directory(root: str, path: str, holds_state: dict[str, bool]) -> bool:
    """Say whether `path` lies in a directory holding Facere's state, as another `--out` leaves one, caching each directory's answer in `holds_state`."""
    for directory in iter_self_and_parents(posixpath.dirname(path)):
        if directory not in holds_state:
            state = os.path.join(root, directory, STATE_DIR_NAME, STATE_FILE_NAME)
            holds_state[directory] = os.path.isfile(state)
        if holds_state[directory]:
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
                rows=rows,
                values=values,
                location=location,
                origin=origin,
            )
        )
        return fn

    return declare if fn is None else declare(fn)
