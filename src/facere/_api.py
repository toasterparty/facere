"""The decorators and helpers a fac.py calls to define rules and tasks."""

import os
import posixpath
from collections.abc import Callable, Iterable
from pathlib import PurePosixPath
from typing import Annotated, Any, TypeVar, overload

from facere._context import Declaration, Kind, find_context, get_context, normalize
from facere._diagnostics import Diagnostic, FacereError, find_caller_location
from facere._version import VERSION

Input = Annotated[str, Kind.INPUT]
Output = Annotated[str, Kind.OUTPUT]

_F = TypeVar("_F", bound=Callable[..., object])


@overload
def rule(fn: _F, /) -> _F: ...


@overload
def rule(
    *,
    each: Iterable[tuple[Any, ...]] | None = None,
    name: str | None = None,
    default: bool = False,
    **values: Any,
) -> Callable[[_F], _F]: ...


def rule(
    fn: _F | None = None,
    /,
    *,
    each: Iterable[tuple[Any, ...]] | None = None,
    name: str | None = None,
    default: bool = False,
    **values: Any,
) -> _F | Callable[[_F], _F]:
    """Define rules from a function, returned unchanged.

    The function's signature declares what each rule reads and writes: a parameter annotated `fac.Input` or `list[fac.Input]` holds the files or directories it reads, one annotated `fac.Output` or `list[fac.Output]` files or directories it writes, and any other parameter a value. `each=` takes an iterable of tuples, read once here, and defines one rule per tuple, filling the leading parameters in order. Keyword arguments fill the parameters they name in every rule, and defaults fill the rest. `name=` replaces the function's name, less one trailing underscore, on the command line, and `default=True` builds the rules when `fac` gets no targets.
    """
    rows = None if each is None else tuple(each)
    return _declarator(fn, is_task=False, name=name, is_default=default, rows=rows, values=values)


@overload
def task(fn: _F, /) -> _F: ...


@overload
def task(
    *, name: str | None = None, default: bool = False, **values: Any
) -> Callable[[_F], _F]: ...


def task(
    fn: _F | None = None, /, *, name: str | None = None, default: bool = False, **values: Any
) -> _F | Callable[[_F], _F]:
    """Define a task from a function, returned unchanged.

    A task takes inputs and values only, and executes whenever a target reaches it, after the rules that output its inputs, with its commands sharing Facere's standard streams. `name=`, `default=True`, and keyword arguments mean what they mean for `fac.rule`.
    """
    return _declarator(fn, is_task=True, name=name, is_default=default, rows=None, values=values)


def out(path: str, suffix: str | None = None) -> str:
    """Return the mirror of `path` inside the output directory, with its suffix swapped for `suffix` when given.

    `fac.out("src/a.c", ".o")` is `build/src/a.o`, and `fac.out(".")` is the output directory itself. A path already inside the output directory keeps its place.
    """
    context = get_context("fac.out")
    relative = normalize(path, context.root)
    if relative == context.out_dir or relative.startswith(f"{context.out_dir}/"):
        mirrored = relative
    elif os.path.isabs(relative) or relative == ".." or relative.startswith("../"):
        raise ValueError(f"fac.out takes a path under the root, not {path!r}")
    else:
        mirrored = posixpath.normpath(posixpath.join(context.out_dir, relative))
    if suffix is None:
        return mirrored
    return PurePosixPath(mirrored).with_suffix(suffix).as_posix()


def minimum_version(version: str) -> None:
    """Fail collection unless the running Facere is `version` or newer, as in `fac.minimum_version("0.1")`."""
    required = _parse_version(version)
    running = _parse_version(VERSION)
    width = max(len(required), len(running))
    if running + (0,) * (width - len(running)) >= required + (0,) * (width - len(required)):
        return
    context = find_context()
    location = find_caller_location(context.fac_py if context else None)
    raise FacereError(
        Diagnostic(
            location,
            f"this project needs Facere {version} or newer, and Facere {VERSION} is running: upgrade it with `uv tool upgrade facere`",
        )
    )


def _parse_version(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if not all(part.isdecimal() for part in parts):
        raise ValueError(f'fac.minimum_version takes a version such as "0.1", not {version!r}')
    return tuple(int(part) for part in parts)


def _declarator(
    fn: _F | None,
    *,
    is_task: bool,
    name: str | None,
    is_default: bool,
    rows: tuple[object, ...] | None,
    values: dict[str, object],
) -> _F | Callable[[_F], _F]:
    def declare(fn: _F) -> _F:
        context = get_context("@fac.task" if is_task else "@fac.rule")
        location = find_caller_location(context.fac_py)
        context.declarations.append(
            Declaration(
                is_task=is_task,
                fn=fn,
                name=name,
                is_default=is_default,
                rows=rows,
                values=values,
                location=location,
            )
        )
        return fn

    return declare if fn is None else declare(fn)
