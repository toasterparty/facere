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
import types
import typing
from collections.abc import Callable, Container, Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

from facere._api import Args
from facere._context import (
    Context,
    Declaration,
    Kind,
    Location,
    Pool,
    calc_path_key,
    is_under_root,
    is_within,
    is_within_any,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note
from facere._engine import Graph, Step
from facere._hash import (
    UnhashableValueError,
    calc_code_text,
    calc_unfingerprinted_digest,
    feed,
    feed_value,
    find_closure_values,
    find_read_globals,
    iter_strings,
    parse,
)
from facere._version import VERSION

MODULE_NAME = "__fac__"
_RESERVED_OPTIONS = ("each", "name", "default", "pool", "always", "clear")
_FINGERPRINT_FORMAT = b"facere fingerprint 8"
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

    `args_slot` places a task's fac.Args parameter: an index into `args`, a key of `kwargs`, or None when it has none. `path_values` holds the paths of each fac.Input, fac.OrderOnly, and fac.Output parameter.
    """

    is_task: bool
    name: str
    location: Location
    origin: Location
    is_default: bool
    is_always: bool
    pool: Pool | None
    fn: Callable[..., object]
    args: tuple[object, ...]
    kwargs: dict[str, object]
    inputs: tuple[str, ...]
    order_only: tuple[str, ...]
    outputs: tuple[str, ...]
    values: dict[str, object]
    text_values: dict[str, object]
    path_values: dict[str, object]
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
    """A root's rules and tasks. `graph` holds one step per definition, in order, whose keys are paths as normalize returns them, `pool_sizes` how many steps of each pool the graph names may run at once, and `producers_by_key` maps the path key of each output to its rule. `unfingerprinted` maps each of the project's Python files that loading imported, as normalize returns it, to a digest of its code that no fingerprint holds, and `epoch` is what fac.epoch set."""

    definitions: tuple[Definition, ...]
    by_name: dict[str, list[Definition]]
    graph: Graph
    pool_sizes: dict[str, int]
    producers_by_key: dict[str, Definition]
    shared_modules: frozenset[str]
    unfingerprinted: dict[str, str]
    epoch: int


def collect(context: Context) -> Project:
    """Load the root's fac.py and return its validated rules and tasks, raising one FacereError listing every problem found."""
    context.is_loading = True
    try:
        imported = _load(context)
    finally:
        context.is_loading = False
    errors: list[Diagnostic] = []
    trees: dict[str, ast.Module] = {}
    _validate_imports(context, imported, trees, errors)
    definitions = tuple(_define_all(context, errors))
    _validate_outputs(context, definitions, errors)
    producers = {output: definition for definition in definitions for output in definition.outputs}
    by_name: dict[str, list[Definition]] = {}
    for definition in definitions:
        by_name.setdefault(definition.name, []).append(definition)
    _validate_names(by_name, errors)
    outputs_by_key = {calc_path_key(output): output for output in producers}
    producers_by_key = {key: producers[output] for key, output in outputs_by_key.items()}
    related = _map_related_outputs(definitions, outputs_by_key)
    code_digests = _hash_values(context, definitions, producers_by_key.keys(), trees, errors)
    _validate_inputs(context, definitions, producers, outputs_by_key, related, errors)
    if errors:
        raise FacereError(*errors)
    pools = {
        definition.pool: f"pool {number}"
        for number, definition in enumerate(definitions)
        if definition.pool is not None
    }
    graph = _build_graph(definitions, related, code_digests, pools)
    if graph.cycle is not None:
        raise FacereError(_build_cycle_error(definitions, graph.cycle, related))
    shared_modules = frozenset(calc_path_key(normalize(path, context.root)) for path in imported)
    pool_sizes = {name: pool.size for pool, name in pools.items()}
    return Project(
        definitions,
        by_name,
        graph,
        pool_sizes,
        producers_by_key,
        shared_modules,
        _hash_unfingerprinted(context, definitions, imported, trees),
        context.epoch,
    )


def _hash_unfingerprinted(
    context: Context,
    definitions: tuple[Definition, ...],
    imported: list[str],
    trees: dict[str, ast.Module],
) -> dict[str, str]:
    """Return calc_unfingerprinted_digest of each of the `imported` sources, by path, treating every recipe and the function it wraps as fingerprinted, a task's too, since a task executes whenever requested. A source a rule inputs is left out whole, since its content joins that rule's fingerprint."""
    recipes = [
        code.__code__
        for declaration in context.declarations
        if isinstance(declaration.fn, types.FunctionType)
        for code in _find_recipe_code(declaration.fn)
    ]
    input_keys = {
        calc_path_key(path)
        for definition in definitions
        if not definition.is_task
        for path in definition.inputs
    }
    digests = {}
    for path in imported:
        relative = normalize(path, context.root)
        if is_within_any(calc_path_key(relative), input_keys):
            continue
        try:
            digests[relative] = calc_unfingerprinted_digest(path, recipes, trees)
        except _UNREADABLE_SOURCE:
            continue
    return digests


def _map_related_outputs(
    definitions: tuple[Definition, ...], outputs_by_key: dict[str, str]
) -> dict[str, tuple[str, ...]]:
    """Map each path a definition must have built first to the outputs that reading it reads: the path itself, a directory holding it, and each path inside it, as a directory input reads every file it holds."""
    keys = sorted(outputs_by_key)
    related: dict[str, tuple[str, ...]] = {}
    for definition in definitions:
        for path in definition.prerequisites:
            if path in related:
                continue
            key = calc_path_key(path)
            exact = [path] if outputs_by_key.get(key) == path else []
            holding = [
                outputs_by_key[parent]
                for parent in iter_self_and_parents(posixpath.dirname(key))
                if parent in outputs_by_key
            ]
            inside = [outputs_by_key[inner] for inner in _find_keys_inside(key, keys)]
            related[path] = tuple(dict.fromkeys([*exact, *holding, *inside]))
    return related


def _build_graph(
    definitions: tuple[Definition, ...],
    related: dict[str, tuple[str, ...]],
    code_digests: dict[Definition, bytes],
    pools: dict[Pool, str],
) -> Graph:
    """Return a step per definition, ordered after the rule of each output related to a path the definition must have built first. Only an input's own content makes its step stale, so every other related output is order-only."""
    steps = []
    for definition in definitions:
        outputs = [output for path in definition.prerequisites for output in related[path]]
        order_only = definition.order_only
        if outputs:
            inputs = frozenset(definition.inputs)
            order_only = tuple(
                dict.fromkeys(path for path in (*order_only, *outputs) if path not in inputs)
            )
        steps.append(
            Step(
                code_digests.get(definition, b"").hex(),
                definition.inputs,
                order_only,
                definition.outputs,
                definition.is_always,
                None if definition.pool is None else pools[definition.pool],
            )
        )
    return Graph(steps)


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
    import traceback

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


def _validate_imports(
    context: Context, imported: list[str], trees: dict[str, ast.Module], errors: list[Diagnostic]
) -> None:
    """Fail each import in the `imported` sources that resolves outside the root, though the root holds a module of that name, parsing each into `trees`."""
    for path in imported:
        for node in ast.walk(parse(path, trees)):
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
    if not held or module is None or is_from_root(context.root, module):
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


def is_from_root(root: str, module: types.ModuleType) -> bool:
    """Say whether `module` was imported from under `root`, a namespace package by any of its directories."""
    paths = [getattr(module, "__file__", None), *getattr(module, "__path__", ())]
    return any(isinstance(path, str) and is_under_root(path, root) for path in paths)


def _is_project_source(context: Context, path: str) -> bool:
    """Say whether `path` is Python the project wrote: under the root, outside the output directory, and in no hidden directory, where a virtual environment lives."""
    return path.endswith(".py") and _is_project_path(context, path)


def _is_project_path(context: Context, path: str) -> bool:
    if not is_under_root(path, context.root):
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
    if declaration.pool is not None and not isinstance(declaration.pool, Pool):
        problems.append(f"pool= takes what fac.pool returned, not {declaration.pool!r}")
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
        pool=declaration.pool if isinstance(declaration.pool, Pool) else None,
        fn=declaration.fn,
        args=args,
        kwargs=kwargs,
        inputs=tuple(paths_by_kind[Kind.INPUT]),
        order_only=tuple(paths_by_kind[Kind.ORDER_ONLY]),
        outputs=tuple(outputs),
        values=values,
        text_values=text_values,
        path_values=path_values,
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
    trees: dict[str, ast.Module],
    errors: list[Diagnostic],
) -> dict[Definition, bytes]:
    """Return each rule's fingerprint of what collection knows: its code, values, and paths, the project's variables, and its epoch. A task records nothing, so neither hashes nor checks its values."""
    function_digests: dict[Callable[..., object], hashlib._Hash | None] = {}
    digests: dict[Definition, bytes] = {}
    env = repr(sorted(context.env.items())).encode()
    for definition in definitions:
        if definition.is_task:
            continue
        if definition.fn not in function_digests:
            function_digests[definition.fn] = _hash_function(
                context, definition, output_keys, trees, errors
            )
        function_digest = function_digests[definition.fn]
        digest = function_digest.copy() if function_digest is not None else hashlib.sha256()
        feed(digest, b"env", env)
        feed(digest, b"epoch", str(context.epoch).encode())
        problems = []
        lambdas: list[types.FunctionType] = []
        for kind, values, keys in (
            ("parameter", definition.values, output_keys),
            ("text parameter", definition.text_values, None),
            ("path parameter", definition.path_values, None),
        ):
            problems.extend(_feed_values(context, digest, kind, values, keys, lambdas))
        problems.extend(_feed_lambdas(context, digest, lambdas, trees))
        errors.extend(
            _diagnose(definition, f"{definition.label} {problem}") for problem in problems
        )
        if function_digest is not None and not problems:
            digests[definition] = digest.digest()
    return digests


def _hash_function(
    context: Context,
    definition: Definition,
    output_keys: Container[str],
    trees: dict[str, ast.Module],
    errors: list[Diagnostic],
) -> hashlib._Hash | None:
    """Return a digest of the code of a rule's recipe and of the function it wraps through `__wrapped__`, which the user decorated, and of what each reads: module constants, a shared module's attributes, and closure variables. Their defaults are the rule's parameters, so join the fingerprint as its values."""
    fn = definition.fn
    assert isinstance(fn, types.FunctionType)
    digest = hashlib.sha256(_FINGERPRINT_FORMAT)
    # A Python minor release may change what the same code does, and changes its syntax trees.
    feed(digest, b"python", f"{sys.version_info.major}.{sys.version_info.minor}".encode())
    problems = []
    lambdas: list[types.FunctionType] = []

    def follow(module: types.ModuleType) -> bool:
        return _is_project_code(context, module)

    for code in _find_recipe_code(fn):
        try:
            feed(digest, b"code", calc_code_text(code, trees).encode())
        except _UNREADABLE_SOURCE as error:
            reach = "has" if code is fn else f"wraps {code.__qualname__}, which has"
            problems.append(
                f"{reach} no source Facere can read, which a rule's fingerprint needs: {error}"
            )
        suffix = "" if code is fn else f" through {code.__qualname__}"
        for kind, values in (
            ("global", find_read_globals(code, follow)),
            ("closure variable", find_closure_values(code)),
        ):
            named = {f"{name}{suffix}": value for name, value in values.items()}
            problems.extend(_feed_values(context, digest, kind, named, output_keys, lambdas))
    problems.extend(_feed_lambdas(context, digest, lambdas, trees))
    errors.extend(
        _diagnose(definition, f"function {fn.__name__} {problem}") for problem in problems
    )
    return None if problems else digest


def _find_recipe_code(fn: types.FunctionType) -> list[types.FunctionType]:
    """Return `fn` and, where a decorator wrapped it, the function it wraps through `__wrapped__`."""
    unwrapped = inspect.unwrap(fn)
    if unwrapped is fn or not isinstance(unwrapped, types.FunctionType):
        return [fn]
    return [fn, unwrapped]


def _feed_lambdas(
    context: Context,
    digest: hashlib._Hash,
    lambdas: list[types.FunctionType],
    trees: dict[str, ast.Module],
) -> list[str]:
    """Feed `digest` the syntax tree of the module defining each of the project's `lambdas`, which no name finds, returning what's wrong with them."""
    problems = []
    for fn in dict.fromkeys(lambdas):
        if not _is_project_code(context, fn):
            continue
        try:
            feed(digest, b"lambda", calc_code_text(fn, trees).encode())
        except _UNREADABLE_SOURCE as error:
            problems.append(
                f"reads a lambda, whose module has no source Facere can read, which a rule's fingerprint needs: {error}"
            )
    return problems


def _is_project_code(context: Context, value: types.ModuleType | types.FunctionType) -> bool:
    """Say whether `value` is a module or function the project wrote, rather than Facere, the standard library, or an installed package."""
    if isinstance(value, types.FunctionType):
        path = value.__code__.co_filename
    else:
        path = getattr(value, "__file__", None)
    # A function that exec defined in a namespace without __name__ has no module.
    module = (value.__name__ if isinstance(value, types.ModuleType) else value.__module__) or ""
    if module == "facere" or module.startswith("facere."):
        return False
    if isinstance(path, str):
        return _is_project_source(context, os.path.abspath(path))
    # A namespace package, a directory without __init__.py, has no file.
    directories = getattr(value, "__path__", ()) if isinstance(value, types.ModuleType) else ()
    return any(
        _is_project_path(context, os.path.abspath(directory))
        for directory in directories
        if isinstance(directory, str)
    )


def _feed_values(
    context: Context,
    digest: hashlib._Hash,
    kind: str,
    values: dict[str, object],
    output_keys: Container[str] | None,
    lambdas: list[types.FunctionType],
) -> list[str]:
    """Feed `values` to `digest`, adding the lambdas they hold to `lambdas`, and return what's wrong with them, checking paths unless `output_keys` is None."""
    problems = []
    for name, value in values.items():
        feed(digest, kind.encode(), name.encode())
        try:
            lambdas.extend(feed_value(digest, value))
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
    outputs_by_key: dict[str, str],
    related: dict[str, tuple[str, ...]],
    errors: list[Diagnostic],
) -> None:
    for definition in definitions:
        for path in definition.prerequisites:
            if not definition.is_task and _holds_out_dir(context, path):
                message = f"{definition.label} inputs {path}, which holds the output directory {context.out_dir}, so its content changes on every build"
                errors.append(_diagnose(definition, message))
                continue
            if related[path]:
                continue
            output = outputs_by_key.get(calc_path_key(path))
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
                if context.observed is not None:
                    context.observed.add_absent(path)
                message = (
                    f"{definition.label} inputs {path}, which doesn't exist, and no rule outputs it"
                )
                errors.append(_diagnose(definition, message))


def _build_cycle_error(
    definitions: tuple[Definition, ...],
    cycle: tuple[tuple[int, str], ...],
    related: dict[str, tuple[str, ...]],
) -> Diagnostic:
    """Return the error for `cycle`, which holds each step with the output of the next that orders it after that one."""
    loop = [definitions[step] for step, _ in cycle]
    names = " -> ".join(definition.label for definition in [*loop, loop[0]])
    notes = []
    for index, (definition, (_, output)) in enumerate(zip(loop, cycle, strict=True)):
        path = next(path for path in definition.prerequisites if output in related[path])
        rule = loop[(index + 1) % len(loop)]
        notes.append(Note(definition.location, _describe_edge(definition, path, rule)))
    return _diagnose(loop[0], f"dependency cycle: {names}", tuple(notes))


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
