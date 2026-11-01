"""Content hashes of values, recipe code, and files, from which fingerprints are built."""

from __future__ import annotations

import ast
import contextlib
import copy
import dis
import hashlib
import os
import stat
import types
from collections.abc import Iterator

_GLOBAL_LOADS = frozenset({"LOAD_GLOBAL", "LOAD_NAME", "LOAD_FROM_DICT_OR_GLOBALS"})


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


def find_read_globals(fn: types.FunctionType) -> dict[str, object]:
    """Return the module globals that the code of `fn`, or of a function nested in it, reads, by name."""
    names: set[str] = set()
    codes = [fn.__code__]
    while codes:
        code = codes.pop()
        names.update(
            instruction.argval
            for instruction in dis.get_instructions(code)
            if instruction.opname in _GLOBAL_LOADS
        )
        codes.extend(const for const in code.co_consts if isinstance(const, types.CodeType))
    return {name: fn.__globals__[name] for name in sorted(names) if name in fn.__globals__}


def find_closure_values(fn: types.FunctionType) -> dict[str, object]:
    """Return the bound closure variables of `fn`, by name."""
    values = {}
    for name, cell in zip(fn.__code__.co_freevars, fn.__closure__ or (), strict=True):
        with contextlib.suppress(ValueError):
            values[name] = cell.cell_contents
    return values


def calc_code_text(fn: types.FunctionType, trees: dict[str, ast.Module]) -> str:
    """Return a dump of the syntax tree of `fn` without positions, decorators, or docstring, parsing its file into `trees` once."""
    code = fn.__code__
    tree = trees.get(code.co_filename)
    if tree is None:
        with open(code.co_filename, "rb") as file:
            tree = trees[code.co_filename] = ast.parse(file.read(), code.co_filename)
    node = next((node for node in ast.walk(tree) if _is_definition_of(node, code)), None)
    if node is None:
        raise LookupError(f"found no source for {fn.__qualname__} in {code.co_filename}")
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    stripped = copy.copy(node)
    stripped.decorator_list = []
    if ast.get_docstring(node, clean=False) is not None:
        stripped.body = node.body[1:]
    return ast.dump(stripped, include_attributes=False)


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
