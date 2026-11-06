"""Content hashes of values, recipe code, and files, from which fingerprints are built."""

from __future__ import annotations

import ast
import contextlib
import copy
import dis
import hashlib
import os
import stat
import sys
import types
import typing
from collections.abc import Callable, Iterator

_GLOBAL_LOADS = frozenset({"LOAD_GLOBAL", "LOAD_NAME", "LOAD_FROM_DICT_OR_GLOBALS"})
_ATTRIBUTE_LOADS = frozenset({"LOAD_ATTR", "LOAD_METHOD"})

_Node = typing.TypeVar("_Node", bound=ast.AST)


class UnhashableValueError(Exception):
    def __init__(self, value: object) -> None:
        cls = type(value)
        self.value = value
        self.type_name = (
            cls.__qualname__
            if cls.__module__ == "builtins"
            else f"{cls.__module__}.{cls.__qualname__}"
        )
        super().__init__(self.type_name)


def feed(digest: hashlib._Hash, tag: bytes, payload: bytes) -> None:
    digest.update(tag)
    digest.update(len(payload).to_bytes(8, "little"))
    digest.update(payload)


def feed_value(digest: hashlib._Hash, value: object) -> None:
    """Feed `value` to `digest` by its type, raising UnhashableValueError for a type Facere doesn't hash."""
    match value:
        case None:
            feed(digest, b"N", b"")
        case bool():
            feed(digest, b"B", b"1" if value else b"0")
        case int():
            feed(digest, b"I", value.to_bytes((value.bit_length() + 8) // 8, "little", signed=True))
        case float():
            feed(digest, b"F", value.hex().encode())
        case str():
            feed(digest, b"S", value.encode("utf-8", "surrogatepass"))
        case bytes():
            feed(digest, b"Y", value)
        case tuple() | list():
            feed(
                digest, b"T" if isinstance(value, tuple) else b"L", len(value).to_bytes(8, "little")
            )
            for item in value:
                feed_value(digest, item)
        case dict():
            feed(digest, b"D", len(value).to_bytes(8, "little"))
            for key, item in value.items():
                feed_value(digest, key)
                feed_value(digest, item)
        case set() | frozenset():
            feed(digest, b"E", len(value).to_bytes(8, "little"))
            for item_digest in sorted(_calc_value_digest(item) for item in value):
                digest.update(item_digest)
        case types.ModuleType():
            feed(digest, b"M", value.__name__.encode())
        case types.FunctionType() | types.BuiltinFunctionType() | type():
            feed(digest, b"Q", f"{value.__module__}.{value.__qualname__}".encode())
        case _:
            raise UnhashableValueError(value)


def _calc_value_digest(value: object) -> bytes:
    digest = hashlib.sha256()
    feed_value(digest, value)
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
    fn: types.FunctionType, follow: Callable[[types.ModuleType], bool] = lambda _: False
) -> dict[str, object]:
    """Return the module globals that the code of `fn`, or of a function nested in it, reads, by name, and the attributes it reads of each module `follow` accepts, by dotted name."""
    values: dict[str, object] = {}
    codes = [fn.__code__]
    while codes:
        code = codes.pop()
        loaded: tuple[str, object] | None = None
        for instruction in dis.get_instructions(code):
            if instruction.opname == "EXTENDED_ARG":
                continue
            loaded = _find_loaded(fn, instruction, loaded, follow)
            if loaded is not None:
                values[loaded[0]] = loaded[1]
        codes.extend(const for const in code.co_consts if isinstance(const, types.CodeType))
    return dict(sorted(values.items()))


def _find_loaded(
    fn: types.FunctionType,
    instruction: dis.Instruction,
    previous: tuple[str, object] | None,
    follow: Callable[[types.ModuleType], bool],
) -> tuple[str, object] | None:
    """Return the dotted name and value `instruction` loads from a global or a followed module's attribute, or None."""
    name = instruction.argval
    if instruction.opname in _GLOBAL_LOADS:
        assert isinstance(name, str)
        return (name, fn.__globals__[name]) if name in fn.__globals__ else None
    if instruction.opname not in _ATTRIBUTE_LOADS or previous is None:
        return None
    module = previous[1]
    if not isinstance(module, types.ModuleType) or not follow(module) or not hasattr(module, name):
        return None
    return f"{previous[0]}.{name}", getattr(module, name)


def find_closure_values(fn: types.FunctionType) -> dict[str, object]:
    """Return the bound closure variables of `fn`, by name."""
    values = {}
    for name, cell in zip(fn.__code__.co_freevars, fn.__closure__ or (), strict=True):
        with contextlib.suppress(ValueError):
            values[name] = cell.cell_contents
    return values


def calc_code_text(
    fn: types.FunctionType, trees: dict[str, ast.Module], keep_decorators: bool = False
) -> str:
    """Return a dump of the syntax tree of `fn` without positions or docstrings, and without decorators unless `keep_decorators`, parsing its file into `trees` once."""
    code = fn.__code__
    tree = _parse(code.co_filename, trees)
    node = next((node for node in ast.walk(tree) if _is_definition_of(node, code)), None)
    if node is None:
        raise LookupError(f"found no source for {fn.__qualname__} in {code.co_filename}")
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    stripped = _strip_docstrings(node)
    if not keep_decorators:
        stripped.decorator_list = []
    return ast.dump(stripped, include_attributes=False)


def calc_class_text(cls: type, trees: dict[str, ast.Module]) -> str:
    """Return a dump of the syntax tree of `cls`, whose module has a source file, without positions or docstrings, or of its whole module where `cls` is defined inside a function, parsing its file into `trees` once."""
    path = getattr(sys.modules.get(cls.__module__), "__file__", None)
    assert isinstance(path, str), f"{cls.__qualname__} has no source file"
    node: ast.AST = _parse(path, trees)
    if "<locals>" not in cls.__qualname__:
        for part in cls.__qualname__.split("."):
            node = _find_child_definition(node, part, path, cls)
    return ast.dump(_strip_docstrings(node), include_attributes=False)


def find_methods(cls: type) -> list[types.FunctionType]:
    """Return the functions `cls` defines itself, unwrapping static methods, class methods, and properties."""
    methods = []
    for value in vars(cls).values():
        match value:
            case staticmethod() | classmethod():
                candidates = [value.__func__]
            case property():
                candidates = [value.fget, value.fset, value.fdel]
            case _:
                candidates = [value]
        methods.extend(item for item in candidates if isinstance(item, types.FunctionType))
    return methods


def _parse(path: str, trees: dict[str, ast.Module]) -> ast.Module:
    tree = trees.get(path)
    if tree is None:
        with open(path, "rb") as file:
            tree = trees[path] = ast.parse(file.read(), path)
    return tree


def _find_child_definition(node: ast.AST, name: str, path: str, cls: type) -> ast.AST:
    body = getattr(node, "body", [])
    child = next(
        (
            child
            for child in body
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and child.name == name
        ),
        None,
    )
    if child is None:
        raise LookupError(f"found no source for {cls.__qualname__} in {path}")
    return child


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


def hash_path(path: str) -> str | None:
    """Return a digest of the file, or of the directory tree, at `path`, or None when nothing is there."""
    try:
        mode = os.stat(path).st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISDIR(mode):
        return _hash_tree(path)
    if stat.S_ISREG(mode):
        return _hash_file(path)
    return "O"


def _hash_file(path: str) -> str:
    with open(path, "rb") as file:
        return "F" + hashlib.file_digest(file, "sha256").hexdigest()


def _hash_tree(path: str) -> str:
    digest = hashlib.sha256()
    with os.scandir(path) as scan:
        entries = sorted(scan, key=lambda entry: entry.name)
    for entry in entries:
        if entry.is_symlink():
            content = "L" + os.readlink(entry.path)
        elif entry.is_dir():
            content = _hash_tree(entry.path)
        elif entry.is_file():
            content = _hash_file(entry.path)
        else:
            content = "O"
        feed(digest, b"N", entry.name.encode("utf-8", "surrogateescape"))
        feed(digest, b"C", content.encode("utf-8", "surrogateescape"))
    return "D" + digest.hexdigest()
