"""Collection: loading the root's fac.py, defining its rules and tasks, and validating them before any recipe executes."""

from __future__ import annotations

import ast
import enum
import hashlib
import importlib.util
import inspect
import os
import posixpath
import sys
import traceback
import types
import typing
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import NamedTuple

from facere._context import Context, Declaration, Kind, Location, normalize
from facere._diagnostics import Diagnostic, FacereError, Note
from facere._hash import (
    UnhashableValueError,
    calc_code_text,
    feed,
    feed_value,
    find_closure_values,
    find_read_globals,
    iter_strings,
)
from facere._version import VERSION

MODULE_NAME = "__fac__"
_RESERVED_OPTIONS = ("each", "name", "default", "max_jobs", "terminal", "always")
_FINGERPRINT_FORMAT = b"facere fingerprint 2"
_HASHABLE_FIX = "pass None, a bool, int, float, str, bytes, module, function, or class, or a tuple, list, dict, or set of them"


class _Slot(enum.Enum):
    VALUE = enum.auto()
    TEXT = enum.auto()


class _PathSlot(NamedTuple):
    kind: Kind
    is_list: bool

    @property
    def annotation(self) -> str:
        name = "fac.Input" if self.kind is Kind.INPUT else "fac.Output"
        return f"list[{name}]" if self.is_list else name


@dataclass(frozen=True, slots=True, eq=False)
class Definition:
    """A rule, or a task when `is_task`, with every parameter filled."""

    is_task: bool
    name: str
    location: Location
    is_default: bool
    fn: Callable[..., object]
    args: tuple[object, ...]
    kwargs: dict[str, object]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    values: dict[str, object]
    text_values: dict[str, object]
    path_values: dict[str, object]

    @property
    def label(self) -> str:
        return f"task '{self.name}'" if self.is_task else f"rule '{self.name}' ({self.outputs[0]})"


@dataclass(frozen=True, slots=True)
class Project:
    definitions: tuple[Definition, ...]
    by_name: dict[str, list[Definition]]
    producers: dict[str, Definition]
    code_digests: dict[Definition, bytes]


def collect(context: Context) -> Project:
    """Load the root's fac.py and return its validated rules and tasks, raising one FacereError listing every problem found."""
    _load(context)
    errors: list[Diagnostic] = []
    definitions = tuple(_define_all(context, errors))
    producers = _validate_outputs(context, definitions, errors)
    by_name: dict[str, list[Definition]] = {}
    for definition in definitions:
        by_name.setdefault(definition.name, []).append(definition)
    _validate_names(by_name, errors)
    code_digests = _hash_values(context, definitions, producers, errors)
    _validate_inputs(definitions, producers, errors)
    if not errors:
        _validate_acyclic(definitions, producers, errors)
    if errors:
        raise FacereError(*errors)
    return Project(definitions, by_name, producers, code_digests)


def _load(context: Context) -> None:
    spec = importlib.util.spec_from_file_location(MODULE_NAME, context.fac_py)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    with open(context.fac_py, "rb") as file:
        source = file.read()
    try:
        exec(compile(source, context.fac_py, "exec"), module.__dict__)  # noqa: S102 - running fac.py is collection
    except FacereError:
        raise
    except SyntaxError as error:
        location = Location(error.filename or context.fac_py, error.lineno or 1, error.offset or 1)
        raise FacereError(Diagnostic(location, f"invalid syntax: {error.msg}")) from None
    except (Exception, SystemExit) as error:  # noqa: BLE001 - any error in fac.py fails collection
        raise _to_load_error(context, error) from None


def _to_load_error(context: Context, error: BaseException) -> FacereError:
    frames = traceback.extract_tb(error.__traceback__)
    in_fac_py = [frame for frame in frames if frame.filename == context.fac_py]
    first = frames.index(in_fac_py[0]) if in_fac_py else 0
    report = traceback.TracebackException.from_exception(error)
    report.stack = traceback.StackSummary.from_list(frames[first:])
    innermost = in_fac_py[-1] if in_fac_py else None
    location = (
        Location(context.fac_py, innermost.lineno or 1, (innermost.colno or 0) + 1)
        if innermost
        else None
    )
    message = (
        f"loading fac.py raised {type(error).__name__}: fix the code the traceback above names"
    )
    return FacereError(Diagnostic(location, message), detail="".join(report.format()))


def _define_all(context: Context, errors: list[Diagnostic]) -> Iterable[Definition]:
    module_globals = sys.modules[MODULE_NAME].__dict__
    for declaration in context.declarations:
        problems: list[str] = []
        definitions = _define(context, declaration, module_globals, problems)
        errors.extend(
            Diagnostic(declaration.location, problem) for problem in dict.fromkeys(problems)
        )
        if not problems:
            yield from definitions


def _define(
    context: Context,
    declaration: Declaration,
    module_globals: dict[str, object],
    problems: list[str],
) -> list[Definition]:
    decorator = "fac.task" if declaration.is_task else "fac.rule"
    fn = declaration.fn
    if not isinstance(fn, types.FunctionType):
        problems.append(f"@{decorator} takes a function defined with def, not {type(fn).__name__}")
        return []
    if fn.__code__.co_filename == context.fac_py and fn.__globals__ is not module_globals:
        problems.append(
            "fac.py ran a second time because a module imported it: move what you share into a shared module"
        )
        return []
    signature = inspect.signature(fn)
    name = _calc_name(fn, declaration, problems)
    slots = _classify_parameters(fn, signature, decorator, problems)
    for key in declaration.values:
        if key in _RESERVED_OPTIONS:
            problems.append(f"{decorator} takes no {key}= option in Facere {VERSION}")
        elif key not in signature.parameters:
            problems.append(
                f"{decorator}({key}=...) names no parameter of {fn.__name__}: remove it or rename it to a parameter"
            )
    if problems:
        return []
    definitions = []
    rows = declaration.rows if declaration.rows is not None else ((),)
    for index, row in enumerate(rows):
        if not isinstance(row, tuple):
            problems.append(
                f"each= item {index} is a {type(row).__name__}, not a tuple: write each item as a tuple, such as (source, output)"
            )
            continue
        bound = _bind(signature, row, index, declaration.values, problems)
        if bound is None:
            continue
        definition = _build_definition(
            context, declaration, name, signature, slots, bound, problems
        )
        if definition is not None:
            definitions.append(definition)
    return definitions


def _calc_name(fn: types.FunctionType, declaration: Declaration, problems: list[str]) -> str:
    name = fn.__name__.removesuffix("_") if declaration.name is None else declaration.name
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("-"):
        problems.append(
            f"the name {name!r} can't be typed as a target: pass name= a name without / or \\ that doesn't start with -"
        )
    return str(name)


def _classify_parameters(
    fn: types.FunctionType, signature: inspect.Signature, decorator: str, problems: list[str]
) -> dict[str, _Slot | _PathSlot]:
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception as error:  # noqa: BLE001 - evaluating an annotation runs arbitrary code
        problems.append(
            f"can't read the annotations of {fn.__name__}: {type(error).__name__}: {error}"
        )
        return {}
    slots = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            star = "*" if parameter.kind is parameter.VAR_POSITIONAL else "**"
            problems.append(
                f"{fn.__name__} takes {star}{parameter.name}, which no rule or task can fill: name each parameter"
            )
            continue
        if parameter.name in _RESERVED_OPTIONS:
            problems.append(
                f"parameter {parameter.name} is named after a {decorator} option, so no keyword argument can fill it: rename it"
            )
            continue
        slot = _classify(hints.get(parameter.name, inspect.Parameter.empty))
        if slot is None:
            problems.append(
                f"parameter {parameter.name} has an annotation Facere can't read: annotate it fac.Input, list[fac.Input], fac.Output, or list[fac.Output]"
            )
            continue
        slots[parameter.name] = slot
    return slots


def _classify(hint: object) -> _Slot | _PathSlot | None:
    kind = _find_kind(hint)
    if kind is not None:
        return _PathSlot(kind, is_list=False)
    args = typing.get_args(hint)
    if typing.get_origin(hint) is list and len(args) == 1:
        kind = _find_kind(args[0])
        if kind is not None:
            return _PathSlot(kind, is_list=True)
        if args[0] is str:
            return _Slot.TEXT
    if hint is str:
        return _Slot.TEXT
    return None if _mentions_kind(hint) else _Slot.VALUE


def _find_kind(hint: object) -> Kind | None:
    if typing.get_origin(hint) is not typing.Annotated:
        return None
    base, *metadata = typing.get_args(hint)
    kinds = [item for item in metadata if isinstance(item, Kind)]
    return kinds[0] if base is str and len(kinds) == 1 else None


def _mentions_kind(hint: object) -> bool:
    if isinstance(hint, Kind):
        return True
    return any(_mentions_kind(arg) for arg in typing.get_args(hint))


def _bind(
    signature: inspect.Signature,
    row: tuple[object, ...],
    index: int,
    values: dict[str, object],
    problems: list[str],
) -> dict[str, object] | None:
    positional = [
        p.name
        for p in signature.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if len(row) > len(positional):
        problems.append(
            f"each= item {index} holds {len(row)} values, and the function takes {len(positional)} positional parameters: drop the extra values"
        )
        return None
    bound = dict(zip(positional, row, strict=False))
    conflicts = [
        f"parameter {key} gets a value from both each= and keyword argument {key}=: pass it one way"
        for key in values
        if key in bound
    ]
    bound.update(values)
    missing = [
        f"parameter {p.name} has no value: give it a default, or pass it through each= or a keyword argument"
        for p in signature.parameters.values()
        if p.name not in bound and p.default is p.empty
    ]
    problems.extend([*conflicts, *missing])
    if conflicts or missing:
        return None
    return {p.name: bound.get(p.name, p.default) for p in signature.parameters.values()}


def _build_definition(
    context: Context,
    declaration: Declaration,
    name: str,
    signature: inspect.Signature,
    slots: dict[str, _Slot | _PathSlot],
    bound: dict[str, object],
    problems: list[str],
) -> Definition | None:
    inputs: list[str] = []
    outputs: list[str] = []
    filled: dict[str, object] = {}
    values: dict[str, object] = {}
    text_values: dict[str, object] = {}
    path_values: dict[str, object] = {}
    for parameter, slot in slots.items():
        value = bound[parameter]
        if isinstance(slot, _PathSlot):
            paths = _normalize_paths(context, parameter, slot, value, problems)
            if paths is None:
                continue
            (inputs if slot.kind is Kind.INPUT else outputs).extend(paths)
            value = path_values[parameter] = paths if slot.is_list else paths[0]
        elif slot is _Slot.TEXT:
            text_values[parameter] = value
        else:
            values[parameter] = value
        filled[parameter] = value
    if declaration.is_task and outputs:
        problems.append(
            f"task {name} declares an output, but a task writes no tracked output: make it a rule with @fac.rule, or drop the fac.Output annotation"
        )
    if not declaration.is_task and not outputs:
        problems.append(
            f"rule {name} declares no output: annotate the parameter its recipe writes fac.Output, or make it a task with @fac.task"
        )
    if problems:
        return None
    args = tuple(
        filled[p.name] for p in signature.parameters.values() if p.kind is not p.KEYWORD_ONLY
    )
    kwargs = {
        p.name: filled[p.name] for p in signature.parameters.values() if p.kind is p.KEYWORD_ONLY
    }
    return Definition(
        is_task=declaration.is_task,
        name=name,
        location=declaration.location,
        is_default=declaration.is_default,
        fn=declaration.fn,
        args=args,
        kwargs=kwargs,
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        values=values,
        text_values=text_values,
        path_values=path_values,
    )


def _normalize_paths(
    context: Context, parameter: str, slot: _PathSlot, value: object, problems: list[str]
) -> list[str] | None:
    items = value if slot.is_list else [value]
    if isinstance(items, list | tuple):
        paths = [item for item in items if isinstance(item, str) and item]
        if len(paths) == len(items):
            return [normalize(path, context.root) for path in paths]
    expected = "a list of paths" if slot.is_list else "a path"
    problems.append(
        f"parameter {parameter} is annotated {slot.annotation} but holds {value!r}: pass {expected}, strings with /"
    )
    return None


def _calc_key(path: str) -> str:
    return path.casefold()


def _is_within(path: str, directory: str) -> bool:
    return directory == "." or path == directory or path.startswith(f"{directory}/")


def _validate_outputs(
    context: Context, definitions: tuple[Definition, ...], errors: list[Diagnostic]
) -> dict[str, Definition]:
    claims: dict[str, list[tuple[Definition, str]]] = {}
    state_key = _calc_key(context.state_dir)
    for definition in definitions:
        for output in definition.outputs:
            key = _calc_key(output)
            claims.setdefault(key, []).append((definition, output))
            if _is_within(key, state_key) or _is_within(state_key, key):
                message = f"{definition.label} outputs {output}, which holds Facere's state: output a path inside the output directory instead"
                errors.append(Diagnostic(definition.location, message))
    for claimants in claims.values():
        if len(claimants) > 1:
            notes = tuple(
                Note(definition.location, f"{definition.label} outputs {output}")
                for definition, output in claimants
            )
            message = f"{len(claimants)} outputs claim {claimants[0][1]}, compared without case: give each rule outputs of its own"
            errors.append(Diagnostic(claimants[0][0].location, message, notes))
    return {output: definition for definition in definitions for output in definition.outputs}


def _validate_names(by_name: dict[str, list[Definition]], errors: list[Diagnostic]) -> None:
    for name, group in by_name.items():
        first_by_fn: dict[Callable[..., object], Definition] = {}
        for definition in group:
            first_by_fn.setdefault(definition.fn, definition)
        clashing = (
            list(first_by_fn.values())
            if len(first_by_fn) > 1
            else [definition for definition in group if definition.is_task]
        )
        if len(clashing) < 2:
            continue
        notes = tuple(
            Note(definition.location, f"{definition.label} is defined here")
            for definition in clashing
        )
        errors.append(
            Diagnostic(
                clashing[0].location,
                f"{len(clashing)} definitions share the name {name}: rename all but one, with name= or def",
                notes,
            )
        )


def _hash_values(
    context: Context,
    definitions: tuple[Definition, ...],
    producers: dict[str, Definition],
    errors: list[Diagnostic],
) -> dict[Definition, bytes]:
    output_keys = {_calc_key(output) for output in producers}
    trees: dict[str, ast.Module] = {}
    function_digests: dict[Callable[..., object], hashlib._Hash | None] = {}
    digests: dict[Definition, bytes] = {}
    for definition in definitions:
        if definition.fn not in function_digests:
            function_digests[definition.fn] = _hash_function(
                context, definition, output_keys, trees, errors
            )
        function_digest = function_digests[definition.fn]
        digest = function_digest.copy() if function_digest else hashlib.sha256()
        problems = [
            problem
            for kind, values, keys in (
                ("parameter", definition.values, output_keys),
                ("text parameter", definition.text_values, None),
                ("path parameter", definition.path_values, None),
            )
            for problem in _feed_values(context, digest, kind, values, keys, definition.is_task)
        ]
        errors.extend(
            Diagnostic(definition.location, f"{definition.label} {problem}") for problem in problems
        )
        if function_digest and not problems and not definition.is_task:
            digests[definition] = digest.digest()
    return digests


def _hash_function(
    context: Context,
    definition: Definition,
    output_keys: set[str],
    trees: dict[str, ast.Module],
    errors: list[Diagnostic],
) -> hashlib._Hash | None:
    fn = definition.fn
    assert isinstance(fn, types.FunctionType)
    digest = hashlib.sha256(_FINGERPRINT_FORMAT)
    problems = []
    if not definition.is_task:
        try:
            feed(digest, b"code", calc_code_text(fn, trees).encode())
        except (OSError, LookupError, SyntaxError, ValueError) as error:
            problems.append(
                f"has no source Facere can read, which a rule's fingerprint needs: {error}"
            )
    for kind, values in (
        ("global", find_read_globals(fn)),
        ("closure variable", find_closure_values(fn)),
    ):
        problems.extend(
            _feed_values(context, digest, kind, values, output_keys, definition.is_task)
        )
    errors.extend(
        Diagnostic(definition.location, f"function {fn.__name__} {problem}") for problem in problems
    )
    return None if problems else digest


def _feed_values(
    context: Context,
    digest: hashlib._Hash,
    kind: str,
    values: dict[str, object],
    output_keys: set[str] | None,
    is_task: bool,
) -> list[str]:
    """Feed `values` to `digest` unless `is_task`, and return what's wrong with them, checking paths unless `output_keys` is None."""
    problems = []
    for name, value in values.items():
        if not is_task:
            feed(digest, kind.encode(), name.encode())
            try:
                feed_value(digest, value)
            except UnhashableValueError as error:
                fix = (
                    "write path.as_posix(), since Facere paths are strings with /"
                    if isinstance(error.value, PurePath)
                    else _HASHABLE_FIX
                )
                problems.append(
                    f"reads {kind} {name}, of type {error.type_name}, which Facere can't hash: {fix}"
                )
                continue
        if output_keys is None or isinstance(value, types.ModuleType | types.FunctionType | type):
            continue
        path = next(
            (text for text in iter_strings(value) if _is_path(context, text, output_keys)), None
        )
        if path is None:
            continue
        if kind == "parameter":
            problems.append(
                f"reads parameter {name}, which names the path {path} unannotated: annotate it fac.Input or list[fac.Input], or str or list[str] if its recipe never reads the file"
            )
        else:
            problems.append(
                f"reads {kind} {name}, which names the path {path}: pass the path through a parameter annotated fac.Input or list[fac.Input]"
            )
    return problems


def _is_path(context: Context, text: str, output_keys: set[str]) -> bool:
    if not text or "\0" in text:
        return False
    if _calc_key(posixpath.normpath(text)) in output_keys:
        return True
    path = os.path.abspath(os.path.join(context.root, text))
    return path.startswith(os.path.join(context.root, "")) and os.path.isfile(path)


def _validate_inputs(
    definitions: tuple[Definition, ...], producers: dict[str, Definition], errors: list[Diagnostic]
) -> None:
    output_by_key = {_calc_key(output): output for output in producers}
    for definition in definitions:
        for path in definition.inputs:
            if path in producers:
                continue
            output = output_by_key.get(_calc_key(path))
            if output is not None:
                rule = producers[output]
                message = f"{definition.label} inputs {path}, which differs only in case from {output}: write the path as {rule.label} outputs it"
                errors.append(
                    Diagnostic(
                        definition.location,
                        message,
                        (Note(rule.location, f"{rule.label} outputs {output}"),),
                    )
                )
            elif not os.path.exists(path):
                message = f"{definition.label} inputs {path}, which doesn't exist, and no rule outputs it: create it, fix the path, or define the rule that outputs it"
                errors.append(Diagnostic(definition.location, message))


def _validate_acyclic(
    definitions: tuple[Definition, ...], producers: dict[str, Definition], errors: list[Diagnostic]
) -> None:
    done: set[Definition] = set()
    for start in definitions:
        if start in done:
            continue
        stack = [(start, iter(start.inputs))]
        path_inputs: list[str] = []
        on_path = {start}
        while stack:
            definition, inputs = stack[-1]
            path = next(inputs, None)
            if path is None:
                stack.pop()
                on_path.discard(definition)
                done.add(definition)
                if path_inputs:
                    path_inputs.pop()
                continue
            rule = producers.get(path)
            if rule is None or rule in done:
                continue
            if rule in on_path:
                loop = [entry for entry, _ in stack]
                loop_inputs = [*path_inputs, path]
                first = loop.index(rule)
                errors.append(_build_cycle_error(loop[first:], loop_inputs[first:]))
                return
            path_inputs.append(path)
            on_path.add(rule)
            stack.append((rule, iter(rule.inputs)))


def _build_cycle_error(loop: list[Definition], inputs: list[str]) -> Diagnostic:
    names = " -> ".join(definition.label for definition in [*loop, loop[0]])
    notes = tuple(
        Note(
            definition.location,
            f"{definition.label} inputs {path}, which {loop[(index + 1) % len(loop)].label} outputs",
        )
        for index, (definition, path) in enumerate(zip(loop, inputs, strict=True))
    )
    return Diagnostic(
        loop[0].location,
        f"dependency cycle: {names}: remove one of these inputs to break the loop",
        notes,
    )
