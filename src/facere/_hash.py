"""Content hashes of values, recipe code, and files, from which fingerprints are built."""

from __future__ import annotations

import ast
import contextlib
import copy
import copyreg
import dis
import hashlib
import os
import stat
import sys
import types
import typing
from collections.abc import Callable, Iterator
from pathlib import PurePath

_GLOBAL_LOADS = frozenset({"LOAD_GLOBAL", "LOAD_NAME", "LOAD_FROM_DICT_OR_GLOBALS"})
_ATTRIBUTE_LOADS = frozenset({"LOAD_ATTR", "LOAD_METHOD"})
_FRAME_READERS = frozenset({"locals", "vars", "eval", "exec"})

_Node = typing.TypeVar("_Node", bound=ast.AST)

Stamp = tuple[object, ...]
"""What a stat shows of a file, or of every entry in a directory tree, so a change shows as a different stamp even where the content ends as it was."""


# Pinned, since a new default protocol could take values apart differently and change every fingerprint.
_PICKLE_PROTOCOL = 5

Code = types.FunctionType | type
"""Code a value can hold, whose syntax tree joins a fingerprint when it lies under the root."""


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


def feed_value(digest: hashlib._Hash, value: object) -> list[Code]:
    """Feed `value` to `digest` by its content, taking apart what is no plain container as pickle would, and return the functions and classes held inside it, `value` itself excluded.

    Raises UnhashableValueError for a value pickle can't take apart, a path object, or a value that holds itself.
    """
    held: list[Code] = []
    _feed_value(digest, value, held, frozenset())
    return held


def _feed_value(
    digest: hashlib._Hash, value: object, held: list[Code], enclosing: frozenset[int]
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
    elif isinstance(value, types.FunctionType | types.BuiltinFunctionType | type):
        feed(digest, b"Q", f"{value.__module__}.{value.__qualname__}".encode())
        if enclosing and isinstance(value, types.FunctionType | type):
            held.append(value)
    elif isinstance(value, PurePath):
        raise UnhashableValueError(value, "Facere paths are strings with /")
    elif id(value) in enclosing:
        raise UnhashableValueError(value, "it holds itself")
    else:
        _feed_composite(digest, value, held, enclosing | {id(value)})


def _feed_composite(
    digest: hashlib._Hash, value: object, held: list[Code], enclosing: frozenset[int]
) -> None:
    cls = type(value)
    if cls is tuple or cls is list:
        assert isinstance(value, tuple | list)
        feed(digest, b"T" if cls is tuple else b"L", len(value).to_bytes(8, "little"))
        for item in value:
            _feed_value(digest, item, held, enclosing)
    elif cls is dict:
        assert isinstance(value, dict)
        feed(digest, b"D", len(value).to_bytes(8, "little"))
        for key, item in value.items():
            _feed_value(digest, key, held, enclosing)
            _feed_value(digest, item, held, enclosing)
    elif cls is set or cls is frozenset:
        assert isinstance(value, set | frozenset)
        # Sorted, since a set's iteration order varies with PYTHONHASHSEED.
        feed(digest, b"E", len(value).to_bytes(8, "little"))
        for item_digest in sorted(_calc_item_digest(item, held, enclosing) for item in value):
            digest.update(item_digest)
    else:
        _feed_reduced(digest, value, held, enclosing)


def _feed_reduced(
    digest: hashlib._Hash, value: object, held: list[Code], enclosing: frozenset[int]
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
        _feed_value(digest, list(part) if isinstance(part, Iterator) else part, held, enclosing)


def _calc_item_digest(item: object, held: list[Code], enclosing: frozenset[int]) -> bytes:
    digest = hashlib.sha256()
    _feed_value(digest, item, held, enclosing)
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


def find_default_values(fn: types.FunctionType) -> dict[str, object]:
    """Return the defaults `fn` bound at definition, by parameter name."""
    code = fn.__code__
    defaults = fn.__defaults__ or ()
    names = code.co_varnames[code.co_argcount - len(defaults) : code.co_argcount]
    return {**dict(zip(names, defaults, strict=True)), **(fn.__kwdefaults__ or {})}


def calc_code_text(
    fn: types.FunctionType, trees: dict[str, ast.Module], keep_decorators: bool = False
) -> str:
    """Return a dump of the syntax tree of `fn` without positions or docstrings, and without decorators unless `keep_decorators`, parsing its file into `trees` once. A lambda, which no name finds, dumps its whole module."""
    if fn.__code__.co_name == "<lambda>":
        module = _parse(fn.__code__.co_filename, trees)
        return ast.dump(_strip_docstrings(module), include_attributes=False)
    stripped = _strip_docstrings(_find_function_node(fn, trees))
    if not keep_decorators:
        stripped.decorator_list = []
    return ast.dump(stripped, include_attributes=False)


def find_named_parameters(fn: types.FunctionType, trees: dict[str, ast.Module]) -> frozenset[str]:
    """Return the parameters of `fn` that its body names, so may read: all of them where it names a function that reads its caller's variables, such as `locals`."""
    code = fn.__code__
    parameters = frozenset(code.co_varnames[: code.co_argcount + code.co_kwonlyargcount])
    named = {
        inner.id
        for statement in _find_function_node(fn, trees).body
        for inner in ast.walk(statement)
        if isinstance(inner, ast.Name)
    }
    return parameters if named & _FRAME_READERS else parameters & named


def _find_function_node(
    fn: types.FunctionType, trees: dict[str, ast.Module]
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    code = fn.__code__
    tree = _parse(code.co_filename, trees)
    node = next((node for node in ast.walk(tree) if _is_definition_of(node, code)), None)
    if node is None:
        raise LookupError(f"found no source for {fn.__qualname__} in {code.co_filename}")
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    return node


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
    """Return a digest of the file, or of the directory tree, at `path`, or None when nothing is there.

    A file's digest covers its bytes and, outside Windows, its executable bit. A link inside a tree hashes as its target, or as its text where it dangles or loops back into the tree.
    """
    try:
        mode = os.stat(path).st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISDIR(mode):
        return _hash_tree(path, frozenset({os.path.realpath(path)}))
    if stat.S_ISREG(mode):
        return _hash_file(path, mode)
    return "O"


def _hash_file(path: str, mode: int) -> str:
    with open(path, "rb") as file:
        content = hashlib.file_digest(file, "sha256").hexdigest()
    is_executable = sys.platform != "win32" and bool(mode & stat.S_IXUSR)
    return ("X" if is_executable else "F") + content


def _hash_tree(path: str, enclosing: frozenset[str]) -> str:
    """Return a digest of the tree at `path`, inside the resolved directories `enclosing`, which a link back into them must not enter again."""
    digest = hashlib.sha256()
    with os.scandir(path) as scan:
        entries = sorted(scan, key=lambda entry: entry.name)
    for entry in entries:
        feed(digest, b"N", entry.name.encode("utf-8", "surrogateescape"))
        feed(digest, b"C", _hash_entry(entry, enclosing).encode("utf-8", "surrogateescape"))
    return "D" + digest.hexdigest()


def _hash_entry(entry: os.DirEntry[str], enclosing: frozenset[str]) -> str:
    if entry.is_dir():
        resolved = os.path.realpath(entry.path)
        if resolved in enclosing:
            return "L" + os.readlink(entry.path)
        return _hash_tree(entry.path, enclosing | {resolved})
    if entry.is_file():
        return _hash_file(entry.path, entry.stat().st_mode)
    if entry.is_symlink():
        return "L" + os.readlink(entry.path)
    return "O"


def calc_stamp(path: str) -> Stamp | None:
    """Return the stamp of the file, or of the directory tree, at `path`, following links as hash_path does, or None when nothing is there."""
    try:
        info = os.stat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISDIR(info.st_mode):
        return _calc_tree_stamp(path, frozenset({os.path.realpath(path)}))
    return _to_stamp(info)


def _calc_tree_stamp(path: str, enclosing: frozenset[str]) -> Stamp:
    with os.scandir(path) as scan:
        entries = sorted(scan, key=lambda entry: entry.name)
    stamps: list[object] = []
    for entry in entries:
        resolved = os.path.realpath(entry.path) if entry.is_dir() else None
        if resolved is not None and resolved not in enclosing:
            stamps.append((entry.name, _calc_tree_stamp(entry.path, enclosing | {resolved})))
        else:
            stamps.append((entry.name, _find_entry_stamp(entry, resolved is None)))
    return tuple(stamps)


def _find_entry_stamp(entry: os.DirEntry[str], is_followed: bool) -> Stamp | None:
    """Return the stamp of what `entry` names, or, where it is a link that dangles or that `is_followed` says not to follow, of the link itself, or None where it vanished."""
    for follow_symlinks in (is_followed, False):
        with contextlib.suppress(FileNotFoundError):
            return _to_stamp(entry.stat(follow_symlinks=follow_symlinks))
    return None


def _to_stamp(info: os.stat_result) -> Stamp:
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_mode)


def find_change_time_ns(path: str) -> int | None:
    """Return when the file at `path` last changed, as its file system stamped it, or for a directory the latest such time in its tree, linked directories aside, or None when nothing is there."""
    info = _find_info(path)
    if info is None:
        return None
    if not stat.S_ISDIR(info.st_mode):
        return _read_change_time_ns(info)
    entries = (
        os.path.join(directory, name)
        for directory, subdirectories, names in os.walk(path)
        for name in (*subdirectories, *names)
    )
    infos = [info, *(found for found in map(_find_info, entries) if found is not None)]
    return max(map(_read_change_time_ns, infos))


def _find_info(path: str) -> os.stat_result | None:
    """Return the stat of what `path` names, or of the link itself where it dangles, or None where nothing is there."""
    for follow_symlinks in (True, False):
        with contextlib.suppress(FileNotFoundError):
            return os.stat(path, follow_symlinks=follow_symlinks)
    return None


def _read_change_time_ns(info: os.stat_result) -> int:
    """Return when the file system last stamped a change to the file `info` describes: its ctime, and on Windows, where that is the creation time, the later of it and the mtime."""
    if sys.platform == "win32":
        return max(info.st_mtime_ns, info.st_ctime_ns)
    return info.st_ctime_ns
