"""Collection: loading the root's fac.py, defining its rules and tasks, and validating them before any recipe executes."""

from __future__ import annotations

import ast
import bisect
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
from collections.abc import Callable, Container, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import NamedTuple

from facere._api import Args
from facere._context import (
    Context,
    Declaration,
    Kind,
    Location,
    calc_path_key,
    is_under_root,
    is_within,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note
from facere._hash import (
    Code,
    UnhashableValueError,
    calc_class_text,
    calc_code_text,
    feed,
    feed_value,
    find_closure_values,
    find_default_values,
    find_methods,
    find_named_parameters,
    find_read_globals,
    iter_strings,
)
from facere._version import VERSION

MODULE_NAME = "__fac__"
_RESERVED_OPTIONS = ("each", "name", "default", "max_jobs", "terminal", "always", "clear")
_FINGERPRINT_FORMAT = b"facere fingerprint 6"
_UNREADABLE_SOURCE = (OSError, LookupError, SyntaxError, ValueError)
_PATH_ANNOTATIONS = {
    Kind.INPUT: "fac.Input",
    Kind.ORDER_ONLY: "fac.OrderOnly",
    Kind.OUTPUT: "fac.Output",
}


class _Slot(enum.Enum):
    VALUE = enum.auto()
    TEXT = enum.auto()
    ARGS = enum.auto()


class _PathSlot(NamedTuple):
    kind: Kind
    is_list: bool

    @property
    def annotation(self) -> str:
        name = _PATH_ANNOTATIONS[self.kind]
        return f"list[{name}]" if self.is_list else name


class _Declared(typing.Protocol):
    @property
    def location(self) -> Location: ...

    @property
    def origin(self) -> Location: ...


def _diagnose(subject: _Declared, message: str, notes: tuple[Note, ...] = ()) -> Diagnostic:
    """Return an error at `subject`'s line in the root's fac.py, noting the decorator's own line when a module declared it."""
    if subject.origin != subject.location:
        notes = (Note(subject.origin, "declared here"), *notes)
    return Diagnostic(subject.location, message, notes)


@dataclass(frozen=True, slots=True, eq=False)
class Definition:
    """A rule, or a task when `is_task`, with every parameter filled.

    `args_slot` places a task's fac.Args parameter: an index into `args`, a key of `kwargs`, or None when it has none. `path_values` holds the paths of each fac.Input, fac.OrderOnly, and fac.Output parameter, and `order_only_parameters` names the fac.OrderOnly ones among them.
    """

    is_task: bool
    name: str
    location: Location
    origin: Location
    is_default: bool
    is_always: bool
    fn: Callable[..., object]
    args: tuple[object, ...]
    kwargs: dict[str, object]
    inputs: tuple[str, ...]
    order_only: tuple[str, ...]
    outputs: tuple[str, ...]
    values: dict[str, object]
    text_values: dict[str, object]
    path_values: dict[str, object]
    order_only_parameters: frozenset[str]
    args_slot: int | str | None

    @property
    def prerequisites(self) -> tuple[str, ...]:
        """Return the paths that must be built before this definition executes."""
        return (*self.inputs, *self.order_only)

    @property
    def label(self) -> str:
        return f"task '{self.name}'" if self.is_task else f"rule '{self.name}' ({self.outputs[0]})"

    def calc_call(
        self, task_args: tuple[str, ...] | None
    ) -> tuple[tuple[object, ...], dict[str, object]]:
        """Return the arguments to call the recipe with, `task_args` filling its fac.Args parameter unless None."""
        if task_args is None or self.args_slot is None:
            return self.args, self.kwargs
        if isinstance(self.args_slot, str):
            return self.args, {**self.kwargs, self.args_slot: task_args}
        args = list(self.args)
        args[self.args_slot] = task_args
        return tuple(args), self.kwargs


@dataclass(frozen=True, slots=True)
class Project:
    definitions: tuple[Definition, ...]
    by_name: dict[str, list[Definition]]
    producers: dict[str, Definition]
    producers_by_key: dict[str, Definition]
    upstream: dict[str, tuple[Definition, ...]]
    code_digests: dict[Definition, bytes]
    shared_modules: frozenset[str]


def collect(context: Context) -> Project:
    """Load the root's fac.py and return its validated rules and tasks, raising one FacereError listing every problem found."""
    imported = _load(context)
    errors: list[Diagnostic] = []
    _validate_imports(context, imported, errors)
    definitions = tuple(_define_all(context, errors))
    _validate_outputs(context, definitions, errors)
    producers = {output: definition for definition in definitions for output in definition.outputs}
    by_name: dict[str, list[Definition]] = {}
    for definition in definitions:
        by_name.setdefault(definition.name, []).append(definition)
    _validate_names(by_name, errors)
    producers_by_key = {calc_path_key(output): rule for output, rule in producers.items()}
    upstream = _map_upstream(definitions, producers, producers_by_key)
    code_digests = _hash_values(context, definitions, producers_by_key.keys(), errors)
    _validate_inputs(context, definitions, producers, upstream, errors)
    if not errors:
        _validate_acyclic(definitions, upstream, errors)
    if errors:
        raise FacereError(*errors)
    shared_modules = frozenset(calc_path_key(normalize(path, context.root)) for path in imported)
    return Project(
        definitions, by_name, producers, producers_by_key, upstream, code_digests, shared_modules
    )


def iter_upstream(
    definition: Definition, upstream: dict[str, tuple[Definition, ...]]
) -> Iterator[tuple[str, Definition]]:
    """Yield each path `definition` must have built first, with each rule it must execute after for that path."""
    for path in definition.prerequisites:
        for rule in upstream[path]:
            yield path, rule


def _map_upstream(
    definitions: tuple[Definition, ...],
    producers: dict[str, Definition],
    producers_by_key: dict[str, Definition],
) -> dict[str, tuple[Definition, ...]]:
    """Map each path a definition must have built first to the rules outputting it, a directory holding it, or a path inside it, as a directory input reads every file it holds."""
    keys = sorted(producers_by_key)
    upstream: dict[str, tuple[Definition, ...]] = {}
    for definition in definitions:
        for path in definition.prerequisites:
            if path in upstream:
                continue
            key = calc_path_key(path)
            exact = [producers[path]] if path in producers else []
            holding = [
                producers_by_key[parent]
                for parent in iter_self_and_parents(posixpath.dirname(key))
                if parent in producers_by_key
            ]
            inside = [producers_by_key[inner] for inner in _find_keys_inside(key, keys)]
            upstream[path] = tuple(dict.fromkeys([*exact, *holding, *inside]))
    return upstream


def _find_keys_inside(directory: str, keys: list[str]) -> list[str]:
    """Return the sorted `keys` that lie inside `directory`, a path key as normalize returns it."""
    if directory == ".":
        return [key for key in keys if not key.startswith("../") and not os.path.isabs(key)]
    # "0" follows "/", so the range holds exactly the keys starting with the directory and a "/".
    start = bisect.bisect_left(keys, f"{directory}/")
    return keys[start : bisect.bisect_left(keys, f"{directory}0", start)]


def _load(context: Context) -> list[str]:
    """Execute the root's fac.py and return the project's own source files that it imported, itself included."""
    already_imported = set(sys.modules)
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
    paths = {context.fac_py}
    for name, imported in list(sys.modules.items()):
        path = getattr(imported, "__file__", None)
        if (
            name not in already_imported
            and isinstance(path, str)
            and _is_project_source(context, path)
        ):
            paths.add(os.path.abspath(path))
    return sorted(paths)


def _to_load_error(context: Context, error: BaseException) -> FacereError:
    frames = traceback.extract_tb(error.__traceback__)
    in_fac_py = [frame for frame in frames if frame.filename == context.fac_py]
    first = frames.index(in_fac_py[0]) if in_fac_py else 0
    report = traceback.TracebackException.from_exception(error)
    report.stack = traceback.StackSummary.from_list(frames[first:])
    location = None
    if in_fac_py:
        innermost = in_fac_py[-1]
        location = Location(context.fac_py, innermost.lineno or 1, (innermost.colno or 0) + 1)
    message = f"loading fac.py raised {type(error).__name__}"
    return FacereError(Diagnostic(location, message), detail="".join(report.format()))


def _validate_imports(context: Context, imported: list[str], errors: list[Diagnostic]) -> None:
    """Fail each import in the `imported` sources that resolves outside the root, though the root holds a module of that name."""
    for path in imported:
        with open(path, "rb") as file:
            tree = ast.parse(file.read(), path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            location = Location(path, node.lineno, node.col_offset + 1)
            for name in _find_imported_names(node):
                diagnostic = _check_import(context, location, name)
                if diagnostic is not None:
                    errors.append(diagnostic)


def _find_imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.partition(".")[0] for alias in node.names]
    if node.level == 0 and node.module is not None:
        return [node.module.partition(".")[0]]
    return []


def _check_import(context: Context, location: Location, name: str) -> Diagnostic | None:
    candidates = [(f"{name}.py", f"{name}.py"), (f"{name}/__init__.py", f"{name}/")]
    held = [shown for path, shown in candidates if os.path.isfile(os.path.join(context.root, path))]
    module = sys.modules.get(name)
    if not held or module is None or _is_from_root(context, module):
        return None
    cause = f"since an earlier sys.path entry shadows {held[0]}"
    path = getattr(module, "__file__", None)
    if not isinstance(path, str):
        message = (
            f"import {name} resolves to a built-in module, though the root holds {held[0]}, {cause}"
        )
        return Diagnostic(location, message)
    message = f"import {name} resolves outside the root, though the root holds {held[0]}, {cause}"
    return Diagnostic(location, message, (Note(Location(path, 1, 1), f"{name} resolves here"),))


def _is_from_root(context: Context, module: types.ModuleType) -> bool:
    paths = [getattr(module, "__file__", None), *getattr(module, "__path__", ())]
    return any(isinstance(path, str) and is_under_root(path, context.root) for path in paths)


def _is_project_source(context: Context, path: str) -> bool:
    """Say whether `path` is Python the project wrote: under the root, outside the output directory, and in no hidden directory, where a virtual environment lives."""
    if not path.endswith(".py") or not is_under_root(path, context.root):
        return False
    relative = normalize(path, context.root)
    parts = relative.split("/")
    return not is_within(relative, context.out_dir) and not any(
        part.startswith(".") for part in parts
    )


def _define_all(context: Context, errors: list[Diagnostic]) -> Iterable[Definition]:
    module_globals = sys.modules[MODULE_NAME].__dict__
    for declaration in context.declarations:
        problems: list[str] = []
        definitions = _define(context, declaration, module_globals, problems)
        errors.extend(_diagnose(declaration, problem) for problem in dict.fromkeys(problems))
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
    if _is_foreign_fac_py(context, fn.__code__.co_filename):
        problems.append(
            "this definition comes from another project's fac.py, which a module imported"
        )
        return []
    if fn.__code__.co_filename == context.fac_py and fn.__globals__ is not module_globals:
        problems.append("fac.py ran a second time because a module imported it")
        return []
    signature = inspect.signature(fn)
    name = _calc_name(fn, declaration, problems)
    slots = _classify_parameters(fn, signature, decorator, problems)
    for key in declaration.values:
        if key in _RESERVED_OPTIONS:
            problems.append(f"{decorator} takes no {key}= option in Facere {VERSION}")
        elif key not in signature.parameters:
            problems.append(f"{decorator}({key}=...) names no parameter of {fn.__name__}")
    if problems:
        return []
    definitions = []
    rows = declaration.rows if declaration.rows is not None else ({},)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"each= item {index} is a {type(row).__name__}, not a dict")
            continue
        bound = _bind(signature, slots, row, index, declaration.values, problems)
        if bound is None:
            continue
        definition = _build_definition(
            context, declaration, name, signature, slots, bound, problems
        )
        if definition is not None:
            definitions.append(definition)
    return definitions


def _is_foreign_fac_py(context: Context, path: str) -> bool:
    if os.path.basename(path) != "fac.py":
        return False
    return os.path.normcase(os.path.abspath(path)) != os.path.normcase(context.fac_py)


def _calc_name(fn: types.FunctionType, declaration: Declaration, problems: list[str]) -> str:
    name = fn.__name__.removesuffix("_") if declaration.name is None else declaration.name
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("-"):
        problems.append(f"the name {name!r} can't be typed as a target")
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
                f"{fn.__name__} takes {star}{parameter.name}, which no rule or task can fill"
            )
            continue
        if parameter.name in _RESERVED_OPTIONS:
            problems.append(
                f"parameter {parameter.name} is named after a {decorator} option, so no keyword argument can fill it"
            )
            continue
        slot = _classify(hints.get(parameter.name, inspect.Parameter.empty))
        if slot is None:
            problems.append(
                f"parameter {parameter.name} has an annotation Facere can't read, and reads only fac.Input, list[fac.Input], fac.OrderOnly, list[fac.OrderOnly], fac.Output, list[fac.Output], and fac.Args"
            )
            continue
        slots[parameter.name] = slot
    return slots


def _classify(hint: object) -> _Slot | _PathSlot | None:
    if hint == Args:
        return _Slot.ARGS
    if hint is str:
        return _Slot.TEXT
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
    return None if _mentions_kind(hint) else _Slot.VALUE


def _find_kind(hint: object) -> Kind | None:
    if typing.get_origin(hint) is not typing.Annotated:
        return None
    base, *metadata = typing.get_args(hint)
    kinds = [item for item in metadata if isinstance(item, Kind)]
    if base is not str or len(kinds) != 1 or kinds[0] is Kind.ARGS:
        return None
    return kinds[0]


def _mentions_kind(hint: object) -> bool:
    if isinstance(hint, Kind):
        return True
    return any(_mentions_kind(arg) for arg in typing.get_args(hint))


def _bind(
    signature: inspect.Signature,
    slots: dict[str, _Slot | _PathSlot],
    row: Mapping[typing.Any, object],
    index: int,
    values: dict[str, object],
    problems: list[str],
) -> dict[str, object] | None:
    unknown = [
        f"each= item {index} fills {key!r}, which names no parameter"
        for key in row
        if key not in signature.parameters
    ]
    conflicts = [
        f"parameter {key} gets a value from both each= and keyword argument {key}="
        for key in values
        if key in row
    ]
    bound = {**row, **values}
    filled_args = [
        f"parameter {name} is annotated fac.Args, so only the command line fills it"
        for name, slot in slots.items()
        if slot is _Slot.ARGS and name in bound
    ]
    for name, slot in slots.items():
        if slot is _Slot.ARGS and signature.parameters[name].default is inspect.Parameter.empty:
            bound.setdefault(name, ())
    missing = [
        f"parameter {p.name} has no value"
        for p in signature.parameters.values()
        if p.name not in bound and p.default is p.empty
    ]
    problems.extend([*unknown, *conflicts, *filled_args, *missing])
    if unknown or conflicts or filled_args or missing:
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
    paths_by_kind: dict[Kind, list[str]] = {kind: [] for kind in _PATH_ANNOTATIONS}
    filled: dict[str, object] = {}
    values: dict[str, object] = {}
    text_values: dict[str, object] = {}
    path_values: dict[str, object] = {}
    args_parameters = []
    are_paths_valid = True
    for parameter, slot in slots.items():
        value = bound[parameter]
        if slot is _Slot.ARGS:
            args_parameters.append(parameter)
        elif isinstance(slot, _PathSlot):
            paths = _normalize_paths(context, parameter, slot, value, problems)
            if paths is None:
                are_paths_valid = False
                continue
            paths_by_kind[slot.kind].extend(paths)
            value = path_values[parameter] = paths if slot.is_list else paths[0]
        elif slot is _Slot.TEXT:
            text_values[parameter] = value
        else:
            values[parameter] = value
        filled[parameter] = value
    outputs = paths_by_kind[Kind.OUTPUT]
    if declaration.is_task and paths_by_kind[Kind.ORDER_ONLY]:
        problems.append(
            f"task {name} declares a fac.OrderOnly input, which only a rule's record can use, since a task records nothing"
        )
    if declaration.is_task and outputs:
        problems.append(f"task {name} declares an output, but a task writes no tracked output")
    if not declaration.is_task and not outputs and are_paths_valid:
        problems.append(f"rule {name} declares no output")
    if args_parameters and not declaration.is_task:
        problems.append(
            f"rule {name} takes {args_parameters[0]}, annotated fac.Args, but only a task receives the command line's arguments"
        )
    if len(args_parameters) > 1:
        problems.append(
            f"task {name} takes {len(args_parameters)} parameters annotated fac.Args, though only one receives the arguments after --"
        )
    if problems:
        return None
    positional = [p.name for p in signature.parameters.values() if p.kind is not p.KEYWORD_ONLY]
    args = tuple(filled[parameter] for parameter in positional)
    kwargs = {
        p.name: filled[p.name] for p in signature.parameters.values() if p.kind is p.KEYWORD_ONLY
    }
    args_slot = None
    if args_parameters:
        (parameter,) = args_parameters
        args_slot = positional.index(parameter) if parameter in positional else parameter
    return Definition(
        is_task=declaration.is_task,
        name=name,
        location=declaration.location,
        origin=declaration.origin,
        is_default=declaration.is_default,
        is_always=declaration.is_always,
        fn=declaration.fn,
        args=args,
        kwargs=kwargs,
        inputs=tuple(paths_by_kind[Kind.INPUT]),
        order_only=tuple(paths_by_kind[Kind.ORDER_ONLY]),
        outputs=tuple(outputs),
        values=values,
        text_values=text_values,
        path_values=path_values,
        order_only_parameters=frozenset(
            parameter
            for parameter, slot in slots.items()
            if isinstance(slot, _PathSlot) and slot.kind is Kind.ORDER_ONLY
        ),
        args_slot=args_slot,
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
        f"parameter {parameter} is annotated {slot.annotation} but holds {value!r}, not {expected}"
    )
    return None


def _validate_outputs(
    context: Context, definitions: tuple[Definition, ...], errors: list[Diagnostic]
) -> None:
    claims: dict[str, list[tuple[Definition, str]]] = {}
    state_key = calc_path_key(context.state_dir)
    for definition in definitions:
        for output in definition.outputs:
            key = calc_path_key(output)
            claims.setdefault(key, []).append((definition, output))
            if is_within(key, state_key) or is_within(state_key, key):
                message = f"{definition.label} outputs {output}, which holds Facere's state"
                errors.append(_diagnose(definition, message))
    for claimants in claims.values():
        if len(claimants) > 1:
            notes = tuple(
                Note(definition.location, f"{definition.label} outputs {output}")
                for definition, output in claimants
            )
            message = f"{len(claimants)} outputs claim {claimants[0][1]}, compared without case"
            errors.append(_diagnose(claimants[0][0], message, notes))


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
            _diagnose(
                clashing[0],
                f"{len(clashing)} definitions share the name {name}",
                notes,
            )
        )


def _hash_values(
    context: Context,
    definitions: tuple[Definition, ...],
    output_keys: Container[str],
    errors: list[Diagnostic],
) -> dict[Definition, bytes]:
    trees: dict[str, ast.Module] = {}
    function_digests: dict[Callable[..., object], hashlib._Hash | None] = {}
    unread_by_function: dict[Callable[..., object], frozenset[str]] = {}
    digests: dict[Definition, bytes] = {}
    env = repr(sorted(context.env.items())).encode()
    for definition in definitions:
        if definition.fn not in function_digests:
            function_digests[definition.fn] = _hash_function(
                context, definition, output_keys, trees, errors
            )
        function_digest = function_digests[definition.fn]
        digest = function_digest.copy() if function_digest is not None else hashlib.sha256()
        feed(digest, b"env", env)
        if function_digest is not None and definition.fn not in unread_by_function:
            unread_by_function[definition.fn] = _find_unread_order_only(definition, trees)
        unread = unread_by_function.get(definition.fn, frozenset())
        path_values = {
            parameter: paths
            for parameter, paths in definition.path_values.items()
            if parameter not in unread
        }
        problems = []
        held: list[Code] = []
        for kind, values, keys in (
            ("parameter", definition.values, output_keys),
            ("text parameter", definition.text_values, None),
            ("path parameter", path_values, None),
        ):
            problems.extend(
                _feed_values(context, digest, kind, values, keys, definition.is_task, held)
            )
        if not definition.is_task:
            code_values = [*definition.values.values(), *held]
            problems.extend(_feed_held_code(context, digest, code_values, output_keys, trees))
        errors.extend(
            _diagnose(definition, f"{definition.label} {problem}") for problem in problems
        )
        if function_digest is not None and not problems and not definition.is_task:
            digests[definition] = digest.digest()
    return digests


def _find_unread_order_only(definition: Definition, trees: dict[str, ast.Module]) -> frozenset[str]:
    """Return the fac.OrderOnly parameters the recipe of `definition`, whose source is readable, never names, whose paths can therefore change nothing it writes."""
    if not definition.order_only_parameters:
        return frozenset()
    assert isinstance(definition.fn, types.FunctionType)
    return definition.order_only_parameters - find_named_parameters(definition.fn, trees)


def _hash_function(
    context: Context,
    definition: Definition,
    output_keys: Container[str],
    trees: dict[str, ast.Module],
    errors: list[Diagnostic],
) -> hashlib._Hash | None:
    fn = definition.fn
    assert isinstance(fn, types.FunctionType)
    digest = hashlib.sha256(_FINGERPRINT_FORMAT)
    # A Python minor release may change what the same code does, and changes its syntax trees.
    feed(digest, b"python", f"{sys.version_info.major}.{sys.version_info.minor}".encode())
    problems = []
    if definition.is_task:
        for kind, values in (
            ("global", find_read_globals(fn)),
            ("closure variable", find_closure_values(fn)),
        ):
            problems.extend(_feed_values(context, digest, kind, values, output_keys, True, []))
    else:
        try:
            feed(digest, b"code", calc_code_text(fn, trees).encode())
        except _UNREADABLE_SOURCE as error:
            problems.append(
                f"has no source Facere can read, which a rule's fingerprint needs: {error}"
            )
        problems.extend(_feed_reach(context, digest, fn, [fn], output_keys, trees, {fn}))
    errors.extend(
        _diagnose(definition, f"function {fn.__name__} {problem}") for problem in problems
    )
    return None if problems else digest


def _feed_reach(
    context: Context,
    digest: hashlib._Hash,
    recipe: types.FunctionType | None,
    pending: list[types.FunctionType],
    output_keys: Container[str],
    trees: dict[str, ast.Module],
    seen: set[object],
) -> list[str]:
    """Feed `digest` the values that each of `pending` reads, the defaults of all but `recipe` included, and the syntax tree and values of every function and class of the project's they reach that `seen` lacks, returning what's wrong with them."""
    problems = []
    while pending:
        current = pending.pop(0)
        suffix = "" if current is recipe else f" through {current.__qualname__}"
        for kind, values in (
            (
                "global",
                find_read_globals(current, lambda module: _is_project_code(context, module)),
            ),
            ("closure variable", find_closure_values(current)),
            ("default", {} if current is recipe else find_default_values(current)),
        ):
            named = {f"{name}{suffix}": value for name, value in values.items()}
            held: list[Code] = []
            problems.extend(_feed_values(context, digest, kind, named, output_keys, False, held))
            problems.extend(
                _feed_newly_reached(
                    context, digest, [*values.values(), *held], trees, seen, pending
                )
            )
    return problems


def _feed_held_code(
    context: Context,
    digest: hashlib._Hash,
    values: list[object],
    output_keys: Container[str],
    trees: dict[str, ast.Module],
) -> list[str]:
    """Feed `digest` the syntax tree and values of the project's functions and classes among `values`, and of all they reach, returning what's wrong with them."""
    pending: list[types.FunctionType] = []
    seen: set[object] = set()
    problems = _feed_newly_reached(context, digest, values, trees, seen, pending)
    return [*problems, *_feed_reach(context, digest, None, pending, output_keys, trees, seen)]


def _feed_newly_reached(
    context: Context,
    digest: hashlib._Hash,
    values: list[object],
    trees: dict[str, ast.Module],
    seen: set[object],
    pending: list[types.FunctionType],
) -> list[str]:
    """Feed `digest` the syntax tree of the project's code that `values` reach and `seen` lacks, adding the functions whose reads join the fingerprint to `pending`, and return what's wrong with that code."""
    problems = []
    for code in (code for value in values for code in _find_reached(value)):
        if not _is_project_code(context, code) or code in seen:
            continue
        seen.add(code)
        problem = _feed_definition(digest, code, trees)
        if problem is not None:
            problems.append(problem)
            continue
        pending.extend(_find_callables(code, seen))
    return problems


def _find_reached(value: object) -> list[Code]:
    """Return the code that naming `value` reaches: a function, the one its decorators wrap, or a class and those it inherits from."""
    if isinstance(value, types.FunctionType):
        unwrapped = inspect.unwrap(value)
        reached = [value, unwrapped] if unwrapped is not value else [value]
        return [code for code in reached if isinstance(code, types.FunctionType)]
    if isinstance(value, type):
        return list(value.__mro__)
    return []


def _feed_definition(digest: hashlib._Hash, code: Code, trees: dict[str, ast.Module]) -> str | None:
    try:
        text = (
            calc_code_text(code, trees, keep_decorators=True)
            if isinstance(code, types.FunctionType)
            else calc_class_text(code, trees)
        )
    except _UNREADABLE_SOURCE as error:
        return f"reaches {code.__qualname__}, which has no source Facere can read, which a rule's fingerprint needs: {error}"
    feed(digest, b"reached", f"{code.__module__}.{code.__qualname__}".encode())
    feed(digest, b"code", text.encode())
    return None


def _find_callables(value: Code, seen: set[object]) -> list[types.FunctionType]:
    """Return the functions whose reads join a fingerprint once `value` is reached: `value` itself, or a class's methods and those of the classes nested in it."""
    if isinstance(value, types.FunctionType):
        return [value]
    callables = []
    for method in find_methods(value):
        if method not in seen:
            seen.add(method)
            callables.append(method)
    for nested in vars(value).values():
        if (
            isinstance(nested, type)
            and nested not in seen
            and nested.__qualname__.startswith(f"{value.__qualname__}.")
        ):
            seen.add(nested)
            callables.extend(_find_callables(nested, seen))
    return callables


def _is_project_code(context: Context, value: types.ModuleType | Code) -> bool:
    """Say whether `value` is a module, function, or class the project wrote, rather than Facere, the standard library, or an installed package."""
    if isinstance(value, types.FunctionType):
        path = value.__code__.co_filename
    elif isinstance(value, type):
        path = getattr(sys.modules.get(value.__module__), "__file__", None)
    else:
        path = getattr(value, "__file__", None)
    # A function that exec defined in a namespace without __name__ has no module.
    module = (value.__name__ if isinstance(value, types.ModuleType) else value.__module__) or ""
    if module == "facere" or module.startswith("facere."):
        return False
    return isinstance(path, str) and _is_project_source(context, os.path.abspath(path))


def _feed_values(
    context: Context,
    digest: hashlib._Hash,
    kind: str,
    values: dict[str, object],
    output_keys: Container[str] | None,
    is_task: bool,
    held: list[Code],
) -> list[str]:
    """Feed `values` to `digest` unless `is_task`, adding the code they hold to `held`, and return what's wrong with them, checking paths unless `output_keys` is None."""
    problems = []
    for name, value in values.items():
        if not is_task:
            feed(digest, kind.encode(), name.encode())
            try:
                held.extend(feed_value(digest, value))
            except UnhashableValueError as error:
                problems.append(
                    f"reads {kind} {name}, of type {error.type_name}, which Facere can't hash, since {error.reason}"
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
            problems.append(f"reads parameter {name}, which names the path {path} unannotated")
        else:
            problems.append(f"reads {kind} {name}, which names the path {path}")
    return problems


def _is_path(context: Context, text: str, output_keys: Container[str]) -> bool:
    if not text or "\0" in text:
        return False
    if calc_path_key(posixpath.normpath(text)) in output_keys:
        return True
    path = os.path.abspath(os.path.join(context.root, text))
    if not is_under_root(path, context.root) or not os.path.isfile(path):
        return False
    return not is_within(normalize(path, context.root), context.out_dir)


def _holds_out_dir(context: Context, path: str) -> bool:
    out_key = calc_path_key(context.out_dir)
    key = calc_path_key(path)
    if key == "." and (out_key.startswith("../") or os.path.isabs(out_key)):
        return False
    return is_within(out_key, key)


def _validate_inputs(
    context: Context,
    definitions: tuple[Definition, ...],
    producers: dict[str, Definition],
    upstream: dict[str, tuple[Definition, ...]],
    errors: list[Diagnostic],
) -> None:
    output_by_key = {calc_path_key(output): output for output in producers}
    for definition in definitions:
        for path in definition.prerequisites:
            if not definition.is_task and _holds_out_dir(context, path):
                message = f"{definition.label} inputs {path}, which holds the output directory {context.out_dir}, so its content changes on every build"
                errors.append(_diagnose(definition, message))
                continue
            if upstream[path]:
                continue
            output = output_by_key.get(calc_path_key(path))
            if output is not None:
                rule = producers[output]
                message = (
                    f"{definition.label} inputs {path}, which differs only in case from {output}"
                )
                errors.append(
                    _diagnose(
                        definition,
                        message,
                        (Note(rule.location, f"{rule.label} outputs {output}"),),
                    )
                )
            elif not os.path.exists(path):
                message = (
                    f"{definition.label} inputs {path}, which doesn't exist, and no rule outputs it"
                )
                errors.append(_diagnose(definition, message))


def _validate_acyclic(
    definitions: tuple[Definition, ...],
    upstream: dict[str, tuple[Definition, ...]],
    errors: list[Diagnostic],
) -> None:
    done: set[Definition] = set()
    for start in definitions:
        if start in done:
            continue
        stack = [(start, iter_upstream(start, upstream))]
        path_inputs: list[str] = []
        on_path = {start}
        while stack:
            definition, edges = stack[-1]
            path, rule = next(edges, (None, None))
            if path is None or rule is None:
                stack.pop()
                on_path.discard(definition)
                done.add(definition)
                if path_inputs:
                    path_inputs.pop()
                continue
            if rule in done:
                continue
            if rule in on_path:
                loop = [entry for entry, _ in stack]
                loop_inputs = [*path_inputs, path]
                first = loop.index(rule)
                errors.append(_build_cycle_error(loop[first:], loop_inputs[first:]))
                return
            path_inputs.append(path)
            on_path.add(rule)
            stack.append((rule, iter_upstream(rule, upstream)))


def _build_cycle_error(loop: list[Definition], inputs: list[str]) -> Diagnostic:
    names = " -> ".join(definition.label for definition in [*loop, loop[0]])
    notes = tuple(
        Note(definition.location, _describe_edge(definition, path, loop[(index + 1) % len(loop)]))
        for index, (definition, path) in enumerate(zip(loop, inputs, strict=True))
    )
    return _diagnose(loop[0], f"dependency cycle: {names}", notes)


def _describe_edge(definition: Definition, path: str, rule: Definition) -> str:
    if path in rule.outputs:
        return f"{definition.label} inputs {path}, which {rule.label} outputs"
    key = calc_path_key(path)
    holding = next(
        (output for output in rule.outputs if is_within(key, calc_path_key(output))), None
    )
    if holding is not None:
        return (
            f"{definition.label} inputs {path}, which lies in {holding}, which {rule.label} outputs"
        )
    inside = next(output for output in rule.outputs if is_within(calc_path_key(output), key))
    return f"{definition.label} inputs {path}, which holds {inside}, which {rule.label} outputs"
