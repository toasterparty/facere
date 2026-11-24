"""Content hashes of values and recipe code, from which fingerprints are built."""

from __future__ import annotations

import ast
import contextlib
import copy
import copyreg
import dis
import hashlib
import os
import types
import typing
from collections.abc import Callable, Iterator
from pathlib import PurePath

_GLOBAL_LOADS = frozenset({"LOAD_GLOBAL", "LOAD_NAME", "LOAD_FROM_DICT_OR_GLOBALS"})
_ATTRIBUTE_LOADS = frozenset({"LOAD_ATTR", "LOAD_METHOD"})

_Node = typing.TypeVar("_Node", bound=ast.AST)

# Pinned, since a new default protocol could take values apart differently and change every fingerprint.
_PICKLE_PROTOCOL = 4


class UnhashableValueError(Exception):
    def __init__(self, value: object, reason: str) -> None:
        cls = type(value)
        self.value = value
        self.type_name = (
            cls.__qualname__
            if cls.__module__ == "builtins"
            else f"{cls.__module__}.{cls.__qualname__}"
        )
        self.reason = reason
        super().__init__(f"{self.type_name}: {reason}")


def feed(digest: hashlib._Hash, tag: bytes, payload: bytes) -> None:
    digest.update(tag)
    digest.update(len(payload).to_bytes(8, "little"))
    digest.update(payload)


def feed_value(digest: hashlib._Hash, value: object) -> list[types.FunctionType]:
    """Feed `value` to `digest` by its content, taking apart what is no plain container as pickle would, functions, classes, and modules by qualified name, and return the lambdas `value` is or holds, which no name finds.

    Raises UnhashableValueError for a value pickle can't take apart, a path object, `os.environ`, or a value that holds itself.
    """
    lambdas: list[types.FunctionType] = []
    _feed_value(digest, value, lambdas, frozenset())
    return lambdas


def _feed_value(
    digest: hashlib._Hash,
    value: object,
    lambdas: list[types.FunctionType],
    enclosing: frozenset[int],
) -> None:
    cls = type(value)
    if value is None:
        feed(digest, b"N", b"")
    elif cls is bool:
        feed(digest, b"B", b"1" if value else b"0")
    elif cls is int:
        assert isinstance(value, int)
        feed(digest, b"I", value.to_bytes((value.bit_length() + 8) // 8, "little", signed=True))
    elif cls is float:
        assert isinstance(value, float)
        feed(digest, b"F", value.hex().encode())
    elif cls is str:
        assert isinstance(value, str)
        feed(digest, b"S", value.encode("utf-8", "surrogatepass"))
    elif cls is bytes:
        assert isinstance(value, bytes)
        feed(digest, b"Y", value)
    elif isinstance(value, types.ModuleType):
        feed(digest, b"M", value.__name__.encode())
    elif isinstance(value, types.FunctionType | type):
        feed(digest, b"Q", f"{value.__module__}.{value.__qualname__}".encode())
        if isinstance(value, types.FunctionType) and is_lambda(value):
            lambdas.append(value)
    elif isinstance(value, types.BuiltinFunctionType) and _is_unbound(value):
        feed(digest, b"Q", f"{value.__module__}.{value.__qualname__}".encode())
    elif isinstance(value, PurePath):
        raise UnhashableValueError(value, "Facere paths are strings with /")
    elif isinstance(value, type(os.environ)):
        raise UnhashableValueError(
            value, "it is the inherited environment, which stays out of fingerprints"
        )
    elif id(value) in enclosing:
        raise UnhashableValueError(value, "it holds itself")
    else:
        _feed_composite(digest, value, lambdas, enclosing | {id(value)})


def _is_unbound(builtin: types.BuiltinFunctionType) -> bool:
    """Say whether `builtin` belongs to a module, unlike a method bound to an object, such as `"{}!".format`, which pickle takes apart as `getattr` of that object."""
    return builtin.__self__ is None or isinstance(builtin.__self__, types.ModuleType)


def _feed_composite(
    digest: hashlib._Hash,
    value: object,
    lambdas: list[types.FunctionType],
    enclosing: frozenset[int],
) -> None:
    cls = type(value)
    if cls is tuple or cls is list:
        assert isinstance(value, tuple | list)
        feed(digest, b"T" if cls is tuple else b"L", len(value).to_bytes(8, "little"))
        for item in value:
            _feed_value(digest, item, lambdas, enclosing)
    elif cls is dict:
        assert isinstance(value, dict)
        feed(digest, b"D", len(value).to_bytes(8, "little"))
        for key, item in value.items():
            _feed_value(digest, key, lambdas, enclosing)
            _feed_value(digest, item, lambdas, enclosing)
    elif cls is set or cls is frozenset:
        assert isinstance(value, set | frozenset)
        # Sorted, since a set's iteration order varies with PYTHONHASHSEED.
        feed(digest, b"E" if cls is set else b"Z", len(value).to_bytes(8, "little"))
        for item_digest in sorted(_calc_item_digest(item, lambdas, enclosing) for item in value):
            digest.update(item_digest)
    else:
        _feed_reduced(digest, value, lambdas, enclosing)


def _feed_reduced(
    digest: hashlib._Hash,
    value: object,
    lambdas: list[types.FunctionType],
    enclosing: frozenset[int],
) -> None:
    """Feed `value` as pickle takes it apart: the callable that rebuilds it, which names its class, and the arguments and state that callable receives."""
    # Pickle consults copyreg's table before __reduce_ex__, as for re.Pattern.
    registered = copyreg.dispatch_table.get(type(value))
    try:
        reduced = registered(value) if registered else value.__reduce_ex__(_PICKLE_PROTOCOL)
    except Exception as error:  # A custom reduction may raise anything, and collection reports it.
        raise UnhashableValueError(value, f"pickle can't take it apart: {error}") from error
    if isinstance(reduced, str):
        feed(digest, b"G", f"{type(value).__module__}.{reduced}".encode())
        return
    feed(digest, b"R", len(reduced).to_bytes(8, "little"))
    for part in reduced:
        _feed_value(digest, list(part) if isinstance(part, Iterator) else part, lambdas, enclosing)


def _calc_item_digest(
    item: object, lambdas: list[types.FunctionType], enclosing: frozenset[int]
) -> bytes:
    digest = hashlib.sha256()
    _feed_value(digest, item, lambdas, enclosing)
    return digest.digest()


def iter_strings(value: object) -> Iterator[str]:
    """Yield every string `value` holds, directly or through tuples, lists, dicts, and sets."""
    match value:
        case str():
            yield value
        case tuple() | list() | set() | frozenset():
            for item in value:
                yield from iter_strings(item)
        case dict():
            for key, item in value.items():
                yield from iter_strings(key)
                yield from iter_strings(item)


def find_read_globals(
    fn: types.FunctionType, follow: Callable[[types.ModuleType], bool]
) -> dict[str, object]:
    """Return the module globals that the code of `fn`, or of a function nested in it, reads, by name, and the attributes it reads of each module `follow` accepts, by dotted name. A module `follow` accepts is left out where the code only reads its attributes."""
    namespace = fn.__globals__
    values: dict[str, object] = {}
    used_whole: set[str] = set()
    codes = [fn.__code__]
    while codes:
        current = codes.pop()
        loaded: tuple[str, object] | None = None
        for instruction in dis.get_instructions(current):
            if instruction.opname == "EXTENDED_ARG":
                continue
            if (
                loaded is not None
                and instruction.opname not in _ATTRIBUTE_LOADS
                and _is_followed(loaded[1], follow)
            ):
                used_whole.add(loaded[0])
            loaded = _find_loaded(namespace, instruction, loaded, follow)
            if loaded is not None:
                values[loaded[0]] = loaded[1]
        codes.extend(const for const in current.co_consts if isinstance(const, types.CodeType))
    return dict(
        sorted(
            (name, value)
            for name, value in values.items()
            if name in used_whole or not _is_followed(value, follow)
        )
    )


def _is_followed(value: object, follow: Callable[[types.ModuleType], bool]) -> bool:
    return isinstance(value, types.ModuleType) and follow(value)


def _find_loaded(
    namespace: dict[str, object],
    instruction: dis.Instruction,
    previous: tuple[str, object] | None,
    follow: Callable[[types.ModuleType], bool],
) -> tuple[str, object] | None:
    """Return the dotted name and value `instruction` loads from a global or a followed module's attribute, or None."""
    name = instruction.argval
    if instruction.opname in _GLOBAL_LOADS:
        assert isinstance(name, str)
        return (name, namespace[name]) if name in namespace else None
    if instruction.opname not in _ATTRIBUTE_LOADS or previous is None:
        return None
    module = previous[1]
    if not _is_followed(module, follow) or not hasattr(module, name):
        return None
    return f"{previous[0]}.{name}", getattr(module, name)


def find_closure_values(fn: types.FunctionType) -> dict[str, object]:
    """Return the bound closure variables of `fn`, by name."""
    values = {}
    for name, cell in zip(fn.__code__.co_freevars, fn.__closure__ or (), strict=True):
        with contextlib.suppress(ValueError):
            values[name] = cell.cell_contents
    return values


def find_default_values(fn: types.FunctionType) -> dict[str, object]:
    """Return the defaults `fn` bound at definition, by parameter name."""
    code = fn.__code__
    defaults = fn.__defaults__ or ()
    names = code.co_varnames[code.co_argcount - len(defaults) : code.co_argcount]
    return {**dict(zip(names, defaults, strict=True)), **(fn.__kwdefaults__ or {})}


def is_lambda(fn: types.FunctionType) -> bool:
    return fn.__code__.co_name == "<lambda>"


def calc_code_text(fn: types.FunctionType, trees: dict[str, ast.Module]) -> str:
    """Return a dump of the syntax tree of `fn` without positions, docstrings, or decorators, parsing its file into `trees` once. A lambda, which no name finds, dumps its whole module."""
    if is_lambda(fn):
        module = parse(fn.__code__.co_filename, trees)
        return ast.dump(_strip_docstrings(module), include_attributes=False)
    stripped = _strip_docstrings(_find_function_node(fn, trees))
    stripped.decorator_list = []
    return ast.dump(stripped, include_attributes=False)


def _find_function_node(
    fn: types.FunctionType, trees: dict[str, ast.Module]
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    code = fn.__code__
    tree = parse(code.co_filename, trees)
    node = next((node for node in ast.walk(tree) if _is_definition_of(node, code)), None)
    if node is None:
        raise LookupError(f"found no source for {fn.__qualname__} in {code.co_filename}")
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    return node


def parse(path: str, trees: dict[str, ast.Module]) -> ast.Module:
    """Return the syntax tree of the Python file at `path`, parsing it into `trees` once."""
    tree = trees.get(path)
    if tree is None:
        with open(path, "rb") as file:
            tree = trees[path] = ast.parse(file.read(), path)
    return tree


def _strip_docstrings(node: _Node) -> _Node:
    """Return a copy of `node` with the docstring of every module, class, and function in it removed."""
    stripped = copy.deepcopy(node)
    for inner in ast.walk(stripped):
        if not isinstance(
            inner, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        if ast.get_docstring(inner, clean=False) is not None:
            inner.body = inner.body[1:]
    return stripped


def _is_definition_of(node: ast.AST, code: types.CodeType) -> bool:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or node.name != code.co_name:
        return False
    first_line = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    return first_line == code.co_firstlineno
