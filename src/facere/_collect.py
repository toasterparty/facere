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
import re
import sys
import types
import typing
from collections.abc import Callable, Container, Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

from facere._api import Args, FileStore, Virtual
from facere._context import (
    Context,
    Declaration,
    Kind,
    Location,
    Pool,
    calc_path_key,
    is_under_root,
    is_within,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note
from facere._engine import Graph, Step
from facere._hash import (
    UnhashableValueError,
    calc_code_text,
    calc_type_name,
    calc_value_digest,
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
_STORE_METHODS = ("stamp", "read", "update")
# A URI scheme of two characters or more, so a Windows drive letter is none.
_URI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+://")
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
    """A parameter holding paths, or where `is_virtual`, fac.Virtual values."""

    kind: Kind
    is_list: bool
    is_virtual: bool = False

    @property
    def annotation(self) -> str:
        name = _PATH_ANNOTATIONS[self.kind]
        if self.is_virtual:
            name = f"{name}[fac.Virtual]"
        return f"list[{name}]" if self.is_list else name


class _VirtualError(Exception):
    """A fac.Virtual whose store, signature function, or key Facere can't hash, described as what a parameter holds."""


def _calc_identity(owner: str, key: object) -> str:
    """Return 32 hex digits identifying `key` within `owner`, the digest of a store's identity or of a signature function. Raises _VirtualError where Facere can't hash `key`."""
    try:
        hash(key)
        key_digest = calc_value_digest(key)
    except TypeError:
        raise _VirtualError(
            f"a fac.Virtual whose key, of type {calc_type_name(key)}, can't be a dict's key"
        ) from None
    except UnhashableValueError as error:
        raise _VirtualError(
            f"a fac.Virtual whose key, of type {calc_type_name(key)}, Facere can't hash, since {error.reason}"
        ) from None
    return hashlib.sha256(f"{owner}{key_digest}".encode()).hexdigest()[:32]


def _show_key(key: object) -> str:
    return key if isinstance(key, str) else repr(key)


class _Stores:
    """The stores, virtual outputs, and virtual sources the definitions name, as collection meets them.

    `objects` holds the distinct store objects of each identity, by store id, `paths` each FileStore's path, by store id, `entries` each virtual output's store id and fac.Virtual, by engine key, and `sources` each virtual source's fac.Virtual, by engine key.
    """

    def __init__(self, root: str) -> None:
        self.root = root
        self._ids: dict[int, str] = {}
        self.objects: dict[str, list[object]] = {}
        self.paths: dict[str, str] = {}
        self.entries: dict[str, tuple[str, Virtual]] = {}
        self.sources: dict[str, Virtual] = {}

    def add(self, virtual: Virtual) -> str:
        """Return the engine key of the virtual output or virtual source `virtual`, which stays the same across invocations and never equals a path as normalize returns one, since it ends in `/`. Raises _VirtualError where Facere can't hash its store, signature function, or key."""
        if virtual.store is None:
            return self._add_source(virtual)
        store = virtual.store
        store_id = self._ids.get(id(store))
        if store_id is None:
            store_id, path = self._identify(store)
            self._ids[id(store)] = store_id
            self.objects.setdefault(store_id, []).append(store)
            if path is not None:
                self.paths[store_id] = path
        engine_key = f"virtual:{_calc_identity(store_id, virtual.key)}/"
        self.entries.setdefault(engine_key, (store_id, virtual))
        return engine_key

    def _add_source(self, virtual: Virtual) -> str:
        """Return the engine key of the virtual source `virtual`, identified by its key and its signature function's qualified name, so the function's code stays out of it."""
        try:
            function_digest = calc_value_digest(virtual.fingerprint)
        except UnhashableValueError as error:
            raise _VirtualError(
                f"a fac.Virtual whose fingerprint, of type {error.type_name}, Facere can't hash, since {error.reason}"
            ) from None
        engine_key = f"source:{_calc_identity(function_digest, virtual.key)}/"
        self.sources.setdefault(engine_key, virtual)
        return engine_key

    def show(self, engine_key: str, writer: str | None) -> str:
        """Return how messages show a virtual output: its FileStore's path, or else the name of the rule `writer` writing it, followed by its key in brackets, and where neither names it, the fac.Virtual. A virtual source shows as its key."""
        source = self.sources.get(engine_key)
        if source is not None:
            return _show_key(source.key)
        store_id, virtual = self.entries[engine_key]
        prefix = self.paths.get(store_id, writer)
        if prefix is None:
            return repr(virtual)
        return f"{prefix}[{_show_key(virtual.key)}]"

    def _identify(self, store: object) -> tuple[str, str | None]:
        digest = hashlib.sha256()
        if isinstance(store, FileStore):
            path = getattr(store, "path", None)
            if not isinstance(path, str) or not path:
                raise _VirtualError(
                    f"a fac.Virtual whose store, a FileStore, has the path {path!r}, not a path relative to the root"
                )
            normalized = normalize(path, self.root)
            feed(digest, b"file", normalized.encode())
            return digest.hexdigest(), normalized
        missing = [name for name in _STORE_METHODS if not callable(getattr(store, name, None))]
        if missing:
            raise _VirtualError(
                f"a fac.Virtual whose store, of type {calc_type_name(store)}, has no {missing[0]} method, though a store other than a FileStore has stamp, read, and update"
            )
        try:
            feed(digest, b"store", b"")
            feed_value(digest, store)
        except UnhashableValueError as error:
            raise _VirtualError(
                f"a fac.Virtual whose store, of type {calc_type_name(store)}, Facere can't hash, since {error.reason}"
            ) from None
        return digest.hexdigest(), None


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

    `args_slot` places a task's fac.Args parameter: an index into `args`, a key of `kwargs`, or None when it has none. `path_values` holds the paths of each fac.Input, fac.OrderOnly, and fac.Output parameter, and the engine key of each fac.Virtual. `virtual_inputs` and `virtual_outputs` map the engine key of each virtual output the rule reads and writes to its fac.Virtual, `virtual_sources` that of each virtual source it inputs, and `shown_outputs` holds its outputs as messages show them, the paths first.
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
    virtual_inputs: dict[str, Virtual]
    virtual_outputs: dict[str, Virtual]
    virtual_sources: dict[str, Virtual]
    shown_outputs: tuple[str, ...]

    @property
    def prerequisites(self) -> tuple[str, ...]:
        """Return the paths that must be built before this definition executes."""
        return (*self.inputs, *self.order_only)

    @property
    def keys(self) -> tuple[str, ...]:
        """Return the engine key of every output, the paths first, which the rule's record is keyed by."""
        return (*self.outputs, *self.virtual_outputs)

    @property
    def label(self) -> str:
        if self.is_task:
            return f"task '{self.name}'"
        return f"rule '{self.name}' ({self.shown_outputs[0]})"

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


@dataclass(frozen=True, slots=True, eq=False)
class DeclaredStore:
    """A store holding a virtual output some rule declares.

    `id` digests its identity: a FileStore's `path`, as normalize returns it, else its class and attributes. `name` is how messages show it, `code` digests the syntax trees of its class's methods, `attributes` digests what its attributes held as collection ended, and `location` is the first rule declaring one of its virtual outputs.
    """

    id: str
    value: object
    path: str | None
    name: str
    code: str
    attributes: str
    location: Location


class VirtualEntry(NamedTuple):
    """A virtual output by engine key: its store's id, its key, and how messages show it."""

    store: str
    key: object
    text: str


class SourceEntry(NamedTuple):
    """A virtual source by engine key: its key, its signature function, and how messages show it."""

    key: object
    fingerprint: Callable[[typing.Any], object]
    text: str


@dataclass(frozen=True, slots=True)
class Project:
    """A root's rules and tasks. `graph` holds one step per definition, in order, whose keys are paths as normalize returns them and the engine keys of virtual outputs, `pool_sizes` how many steps of each pool the graph names may run at once, and `producers_by_key` maps the path key of each output to its rule.

    `stores` holds each store a rule declares a virtual output of, by id, `virtuals` each virtual output by engine key, and `sources` each virtual source by engine key. `virtual_targets` maps how messages show each virtual output a rule writes to its engine key, and `store_writers` the path key of each FileStore to the rules writing to it.
    """

    definitions: tuple[Definition, ...]
    by_name: dict[str, list[Definition]]
    graph: Graph
    pool_sizes: dict[str, int]
    producers_by_key: dict[str, Definition]
    shared_modules: frozenset[str]
    stores: dict[str, DeclaredStore]
    virtuals: dict[str, VirtualEntry]
    sources: dict[str, SourceEntry]
    virtual_targets: dict[str, str]
    store_writers: dict[str, tuple[Definition, ...]]


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
    stores = _Stores(context.root)
    definitions = tuple(_define_all(context, stores, errors))
    _validate_outputs(context, definitions, errors)
    producers = {output: definition for definition in definitions for output in definition.outputs}
    by_name: dict[str, list[Definition]] = {}
    for definition in definitions:
        by_name.setdefault(definition.name, []).append(definition)
    _validate_names(by_name, errors)
    outputs_by_key = {calc_path_key(output): output for output in producers}
    producers_by_key = {key: producers[output] for key, output in outputs_by_key.items()}
    users = _find_store_users(definitions, stores)
    writers = _validate_virtuals(definitions, stores, users, errors)
    related = _map_related_outputs(definitions, outputs_by_key)
    file_store_outputs = _map_file_store_outputs(stores, writers)
    store_codes = _hash_store_codes(context, stores, users, trees, errors)
    code_digests = _hash_values(
        context, definitions, producers_by_key.keys(), stores, store_codes, trees, errors
    )
    _validate_inputs(
        context, definitions, producers, outputs_by_key, related, file_store_outputs, errors
    )
    declared_stores = _declare_stores(stores, store_codes, users, errors)
    if errors:
        raise FacereError(*errors)
    pools = {
        definition.pool: f"pool {number}"
        for number, definition in enumerate(definitions)
        if definition.pool is not None
    }
    graph = _build_graph(definitions, related, file_store_outputs, code_digests, pools)
    if graph.cycle is not None:
        raise FacereError(_build_cycle_error(definitions, graph.cycle, related, file_store_outputs))
    shared_modules = frozenset(calc_path_key(normalize(path, context.root)) for path in imported)
    pool_sizes = {name: pool.size for pool, name in pools.items()}
    virtuals = {
        key: VirtualEntry(store, virtual.key, stores.show(key, writers[key].name))
        for key, (store, virtual) in stores.entries.items()
        if key in writers
    }
    sources = {}
    for key, virtual in stores.sources.items():
        assert virtual.fingerprint is not None
        sources[key] = SourceEntry(virtual.key, virtual.fingerprint, stores.show(key, None))
    store_writers = {
        calc_path_key(store.path): tuple(
            definition
            for definition in definitions
            if any(virtuals[key].store == store.id for key in definition.virtual_outputs)
        )
        for store in declared_stores.values()
        if store.path is not None
    }
    return Project(
        definitions,
        by_name,
        graph,
        pool_sizes,
        producers_by_key,
        shared_modules,
        declared_stores,
        virtuals,
        sources,
        {entry.text: key for key, entry in virtuals.items()},
        store_writers,
    )


def _map_file_store_outputs(
    stores: _Stores, writers: dict[str, Definition]
) -> dict[str, tuple[str, ...]]:
    """Return the engine key of each virtual output a rule writes to each FileStore, by the path key of its file, which a rule reading the whole file is ordered after."""
    outputs: dict[str, list[str]] = {}
    for key, (store_id, _) in stores.entries.items():
        path = stores.paths.get(store_id)
        if path is not None and key in writers:
            outputs.setdefault(calc_path_key(path), []).append(key)
    return {path_key: tuple(keys) for path_key, keys in outputs.items()}


def _find_store_users(
    definitions: tuple[Definition, ...], stores: _Stores
) -> dict[str, Definition]:
    """Return the first definition declaring a virtual output of each store, by store id."""
    users: dict[str, Definition] = {}
    for definition in definitions:
        for key in (*definition.virtual_outputs, *definition.virtual_inputs):
            users.setdefault(stores.entries[key][0], definition)
    return users


def _validate_virtuals(
    definitions: tuple[Definition, ...],
    stores: _Stores,
    users: dict[str, Definition],
    errors: list[Diagnostic],
) -> dict[str, Definition]:
    """Fail a virtual output two rules write, one a rule reads that no rule writes, a FileStore's path a rule outputs as a file, and two FileStore values on one path, and return the rule writing each virtual output, by engine key."""
    claims: dict[str, list[Definition]] = {}
    for definition in definitions:
        for key in definition.virtual_outputs:
            claims.setdefault(key, []).append(definition)
    for key, claimants in claims.items():
        if len(claimants) < 2:
            continue
        notes = tuple(
            Note(
                definition.location,
                f"{definition.label} outputs {stores.show(key, definition.name)}",
            )
            for definition in claimants
        )
        message = f"{len(claimants)} rules output {stores.show(key, claimants[0].name)}"
        errors.append(_diagnose(claimants[0], message, notes))
    for definition in definitions:
        for key in definition.virtual_inputs:
            if key not in claims:
                message = f"{definition.label} inputs {stores.show(key, None)}, which no rule outputs, though a store is never a source, and an input no rule writes is a fac.Virtual given fingerprint="
                errors.append(_diagnose(definition, message))
    paths = {calc_path_key(path): store_id for store_id, path in stores.paths.items()}
    for definition in definitions:
        for output in definition.outputs:
            user = users.get(paths.get(calc_path_key(output), ""))
            if user is None:
                continue
            message = f"{definition.label} outputs {output}, which holds the virtual outputs of a FileStore"
            note = Note(user.location, f"{user.label} declares a virtual output of it")
            errors.append(_diagnose(definition, message, (note,)))
    for store_id, path in stores.paths.items():
        objects = stores.objects[store_id]
        if len(objects) < 2:
            continue
        first_users = {
            id(virtual.store): definition
            for definition in reversed(definitions)
            for virtual in (
                *definition.virtual_outputs.values(),
                *definition.virtual_inputs.values(),
            )
        }
        sharing = [first_users[id(store)] for store in objects if id(store) in first_users]
        notes = tuple(
            Note(definition.location, f"{definition.label} declares a virtual output of one")
            for definition in sharing
        )
        message = f"{len(objects)} FileStore values share the path {path}"
        errors.append(_diagnose(sharing[0], message, notes))
    return {key: claimants[0] for key, claimants in claims.items()}


def _hash_store_codes(
    context: Context,
    stores: _Stores,
    users: dict[str, Definition],
    trees: dict[str, ast.Module],
    errors: list[Diagnostic],
) -> dict[str, str]:
    """Return the digest of the syntax trees of each store class's methods, by store id, leaving out the code they call and their class's module, as a recipe's fingerprint does."""
    by_class: dict[type, str | None] = {}
    codes = {}
    for store_id, objects in stores.objects.items():
        if store_id not in users:
            continue
        cls = type(objects[0])
        if cls not in by_class:
            by_class[cls] = _hash_store_class(context, cls, trees, users[store_id], errors)
        code = by_class[cls]
        if code is not None:
            codes[store_id] = code
    return codes


def _hash_store_class(
    context: Context,
    cls: type,
    trees: dict[str, ast.Module],
    user: Definition,
    errors: list[Diagnostic],
) -> str | None:
    digest = hashlib.sha256(_FINGERPRINT_FORMAT)
    for klass in cls.__mro__:
        for name, attribute in vars(klass).items():
            fn = attribute
            if isinstance(attribute, staticmethod | classmethod):
                fn = attribute.__func__
            elif isinstance(attribute, property):
                fn = attribute.fget
            if not isinstance(fn, types.FunctionType) or not _is_project_code(context, fn):
                continue
            feed(digest, b"method", f"{klass.__qualname__}.{name}".encode())
            try:
                feed(digest, b"code", calc_code_text(fn, trees).encode())
            except _UNREADABLE_SOURCE as error:
                message = f"store class {cls.__qualname__} has a method {klass.__qualname__}.{name} with no source Facere can read, which the fingerprint of each rule writing to it needs: {error}"
                errors.append(_diagnose(user, message))
                return None
    return digest.hexdigest()


def _declare_stores(
    stores: _Stores,
    codes: dict[str, str],
    users: dict[str, Definition],
    errors: list[Diagnostic],
) -> dict[str, DeclaredStore]:
    """Return each store a definition declares a virtual output of, by store id, with what its attributes hold as collection ends."""
    declared = {}
    for store_id, objects in stores.objects.items():
        user = users.get(store_id)
        if user is None:
            continue
        value = objects[0]
        path = stores.paths.get(store_id)
        name = path or type(value).__qualname__
        try:
            attributes = calc_value_digest(value)
        except UnhashableValueError as error:
            message = f"store {name} holds an attribute of type {error.type_name}, which Facere can't hash, since {error.reason}"
            errors.append(_diagnose(user, message))
            continue
        declared[store_id] = DeclaredStore(
            store_id, value, path, name, codes.get(store_id, ""), attributes, user.location
        )
    return declared


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
    file_store_outputs: dict[str, tuple[str, ...]],
    code_digests: dict[Definition, bytes],
    pools: dict[Pool, str],
) -> Graph:
    """Return a step per definition, ordered after the rule of each output related to a path the definition must have built first, and of each virtual output of a FileStore whose file it inputs. Only an input's own content makes its step stale, so every other related output is order-only."""
    steps = []
    for definition in definitions:
        outputs = [output for path in definition.prerequisites for output in related[path]]
        outputs.extend(
            key
            for path in definition.inputs
            for key in file_store_outputs.get(calc_path_key(path), ())
        )
        order_only = definition.order_only
        if outputs:
            inputs = frozenset(definition.inputs)
            order_only = tuple(
                dict.fromkeys(path for path in (*order_only, *outputs) if path not in inputs)
            )
        steps.append(
            Step(
                code_digests.get(definition, b"").hex(),
                (*definition.inputs, *definition.virtual_inputs, *definition.virtual_sources),
                order_only,
                definition.keys,
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


def _define_all(
    context: Context, stores: _Stores, errors: list[Diagnostic]
) -> Iterable[Definition]:
    module_globals = sys.modules[MODULE_NAME].__dict__
    for declaration in context.declarations:
        problems: list[str] = []
        definitions = _define(context, declaration, module_globals, stores, problems)
        errors.extend(_diagnose(declaration, problem) for problem in dict.fromkeys(problems))
        if not problems:
            yield from definitions


def _define(
    context: Context,
    declaration: Declaration,
    module_globals: dict[str, object],
    stores: _Stores,
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
            context, declaration, name, signature, slots, bound, stores, problems
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
                f"parameter {parameter.name} has an annotation Facere can't read, and reads only fac.Input, fac.OrderOnly, fac.Output, fac.Input[fac.Virtual], and fac.Output[fac.Virtual], each alone or in a list, and fac.Args"
            )
            continue
        slots[parameter.name] = slot
    return slots


def _classify(hint: object) -> _Slot | _PathSlot | None:
    if hint == Args:
        return _Slot.ARGS
    if hint is str:
        return _Slot.TEXT
    slot = _find_path_slot(hint, is_list=False)
    if slot is not None:
        return slot
    args = typing.get_args(hint)
    if typing.get_origin(hint) is list and len(args) == 1:
        slot = _find_path_slot(args[0], is_list=True)
        if slot is not None:
            return slot
        if args[0] is str:
            return _Slot.TEXT
    return None if _mentions_kind(hint) else _Slot.VALUE


def _find_path_slot(hint: object, *, is_list: bool) -> _PathSlot | None:
    """Return the slot of a fac.Input, fac.OrderOnly, or fac.Output annotation, whose bare form subscripts nothing, so its base is a TypeVar meaning str."""
    if typing.get_origin(hint) is not typing.Annotated:
        return None
    base, *metadata = typing.get_args(hint)
    kinds = [item for item in metadata if isinstance(item, Kind)]
    if len(kinds) != 1 or kinds[0] is Kind.ARGS:
        return None
    (kind,) = kinds
    if base is str or isinstance(base, typing.TypeVar):
        return _PathSlot(kind, is_list)
    if base is Virtual and kind is not Kind.ORDER_ONLY:
        return _PathSlot(kind, is_list, is_virtual=True)
    return None


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
    stores: _Stores,
    problems: list[str],
) -> Definition | None:
    paths_by_kind: dict[Kind, list[str]] = {kind: [] for kind in _PATH_ANNOTATIONS}
    virtuals_by_kind: dict[Kind, dict[str, Virtual]] = {Kind.INPUT: {}, Kind.OUTPUT: {}}
    virtual_sources: dict[str, Virtual] = {}
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
        elif isinstance(slot, _PathSlot) and slot.is_virtual:
            keyed = _key_virtuals(stores, parameter, slot, value, problems)
            if keyed is None:
                are_paths_valid = False
                continue
            for key, virtual in keyed:
                held = virtual_sources if virtual.store is None else virtuals_by_kind[slot.kind]
                held[key] = virtual
            keys = [key for key, _ in keyed]
            path_values[parameter] = keys if slot.is_list else keys[0]
            value = [virtual for _, virtual in keyed] if slot.is_list else value
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
    virtual_inputs = virtuals_by_kind[Kind.INPUT]
    virtual_outputs = virtuals_by_kind[Kind.OUTPUT]
    if declaration.is_task and paths_by_kind[Kind.ORDER_ONLY]:
        problems.append(
            f"task {name} declares a fac.OrderOnly input, which only a rule's record can use, since a task records nothing"
        )
    if declaration.is_task and (virtual_inputs or virtual_sources):
        problems.append(
            f"task {name} declares a fac.Input[fac.Virtual], which only a rule's record can track, since a task records nothing"
        )
    if declaration.is_task and (outputs or virtual_outputs):
        problems.append(f"task {name} declares an output, but a task writes no tracked output")
    if not declaration.is_task and not (outputs or virtual_outputs) and are_paths_valid:
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
        virtual_inputs=virtual_inputs,
        virtual_outputs=virtual_outputs,
        virtual_sources=virtual_sources,
        shown_outputs=(
            *outputs,
            *(stores.show(key, name) for key in virtual_outputs),
        ),
    )


def _normalize_paths(
    context: Context, parameter: str, slot: _PathSlot, value: object, problems: list[str]
) -> list[str] | None:
    items = value if slot.is_list else [value]
    if isinstance(items, list | tuple):
        paths = [item for item in items if isinstance(item, str) and item]
        uri = next((path for path in paths if _URI.match(path)), None)
        if uri is not None and slot.kind is Kind.INPUT:
            problems.append(
                f"parameter {parameter} is annotated {slot.annotation} but holds the URI {uri!r}, not a path, and an input that is no file is a fac.Virtual"
            )
            return None
        if len(paths) == len(items):
            return [normalize(path, context.root) for path in paths]
    expected = "a list of paths" if slot.is_list else "a path"
    problems.append(
        f"parameter {parameter} is annotated {slot.annotation} but holds {value!r}, not {expected}"
    )
    return None


def _key_virtuals(
    stores: _Stores, parameter: str, slot: _PathSlot, value: object, problems: list[str]
) -> list[tuple[str, Virtual]] | None:
    """Return the engine key of each virtual output or virtual source a fac.Input[fac.Virtual] or fac.Output[fac.Virtual] parameter holds, with its fac.Virtual, or None where it holds anything else."""
    items = value if slot.is_list else [value]
    if not isinstance(items, list | tuple) or not all(isinstance(item, Virtual) for item in items):
        expected = "a list of fac.Virtual values" if slot.is_list else "a fac.Virtual"
        problems.append(
            f"parameter {parameter} is annotated {slot.annotation} but holds {value!r}, not {expected}"
        )
        return None
    keyed = []
    for virtual in items:
        assert isinstance(virtual, Virtual)
        if virtual.store is None and slot.kind is Kind.OUTPUT:
            problems.append(
                f"parameter {parameter} is annotated {slot.annotation} but holds the virtual source {virtual!r}, which no rule writes, since Facere knows it only by its signature"
            )
            return None
        try:
            keyed.append((stores.add(virtual), virtual))
        except _VirtualError as error:
            problems.append(f"parameter {parameter} holds {error}")
            return None
    return keyed


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
    stores: _Stores,
    store_codes: dict[str, str],
    trees: dict[str, ast.Module],
    errors: list[Diagnostic],
) -> dict[Definition, bytes]:
    """Return each rule's fingerprint of what collection knows: its code, values, and paths, the code of the store of each virtual output it writes, the project's variables, and its epoch. A task records nothing, so neither hashes nor checks its values."""
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
        written = {stores.entries[key][0] for key in definition.virtual_outputs}
        for store_id in sorted(written):
            feed(digest, b"store", store_codes.get(store_id, "").encode())
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
    file_store_outputs: dict[str, tuple[str, ...]],
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
            if path in definition.inputs and calc_path_key(path) in file_store_outputs:
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
    file_store_outputs: dict[str, tuple[str, ...]],
) -> Diagnostic:
    """Return the error for `cycle`, which holds each step with the output of the next that orders it after that one."""
    loop = [definitions[step] for step, _ in cycle]
    names = " -> ".join(definition.label for definition in [*loop, loop[0]])
    notes = []
    for index, (definition, (_, output)) in enumerate(zip(loop, cycle, strict=True)):
        rule = loop[(index + 1) % len(loop)]
        if output in rule.virtual_outputs:
            shown = dict(zip(rule.keys, rule.shown_outputs, strict=True))[output]
            edge = f"{definition.label} inputs {shown}, which {rule.label} outputs"
            if output not in definition.virtual_inputs:
                path = next(
                    path
                    for path in definition.inputs
                    if output in file_store_outputs.get(calc_path_key(path), ())
                )
                edge = f"{definition.label} inputs {path}, which holds {shown}, which {rule.label} outputs"
            notes.append(Note(definition.location, edge))
            continue
        path = next(path for path in definition.prerequisites if output in related[path])
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
