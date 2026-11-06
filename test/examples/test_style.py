"""Every example fac.py, and every fac.py snippet in the user docs but a "# Bad" one, keeps to doc/maintainer/fac-py-style.md."""

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path

_REPO = Path(__file__).parents[2]
_SNIPPET = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)
_FAC_DECORATORS = {"fac.rule", "fac.task"}


def _load_sources() -> Iterator[tuple[str, ast.Module]]:
    for path in sorted((_REPO / "doc" / "examples").glob("**/fac.py")):
        yield path.relative_to(_REPO).as_posix(), ast.parse(path.read_text(encoding="utf-8"))
    for path in sorted((_REPO / "doc" / "user").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in _SNIPPET.finditer(text):
            if match[1].startswith("# Bad"):
                continue
            line = text.count("\n", 0, match.start(1)) + 1
            yield f"{path.relative_to(_REPO).as_posix()}:{line}", ast.parse(match[1])


def _find(is_violation: Callable[[ast.AST], bool]) -> list[str]:
    return [
        f"{where} line {node.lineno}"
        for where, tree in _load_sources()
        for node in ast.walk(tree)
        if is_violation(node) and hasattr(node, "lineno")
    ]


def _is_fac_decorated(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if ast.unparse(target) in _FAC_DECORATORS:
            return True
    return False


def _has_keyword(node: ast.AST, callee: set[str], keyword: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and ast.unparse(node.func) in callee
        and any(item.arg == keyword for item in node.keywords)
    )


def test_annotations_appear_only_where_facere_reads_them() -> None:
    def is_violation(node: ast.AST) -> bool:
        if not isinstance(node, ast.FunctionDef):
            return False
        if node.returns is not None:
            return True
        annotated = any(arg.annotation is not None for arg in node.args.args)
        return annotated and not _is_fac_decorated(node)

    assert _find(is_violation) == []


def test_each_rows_are_dicts_built_without_zip() -> None:
    assert _find(lambda node: isinstance(node, ast.Call) and ast.unparse(node.func) == "zip") == []


def test_text_files_go_through_fac_read_text_and_write_text() -> None:
    assert _find(lambda node: _has_keyword(node, {"open"}, "encoding")) == []


def test_helpers_have_plain_names() -> None:
    def is_violation(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.FunctionDef)
            and node.name.startswith("_")
            and not node.name.startswith("__")
        )

    assert _find(is_violation) == []


def test_lists_join_with_plus_not_unpacking() -> None:
    assert _find(lambda node: isinstance(node, ast.Starred)) == []


def test_data_is_dicts_and_stores_are_plain_classes() -> None:
    def is_violation(node: ast.AST) -> bool:
        if isinstance(node, ast.ImportFrom):
            return node.module in {"dataclasses", "typing", "collections.abc"}
        return isinstance(node, ast.Import) and any(
            alias.name in {"dataclasses", "typing"} for alias in node.names
        )

    assert _find(is_violation) == []


def test_signatures_never_mix_inline_paths_with_named_ones() -> None:
    def is_path(annotation: ast.expr | None) -> bool:
        return annotation is not None and any(
            part in ast.unparse(annotation) for part in ("fac.Input", "fac.Output")
        )

    def is_violation(node: ast.AST) -> bool:
        if not isinstance(node, ast.FunctionDef):
            return False
        args = node.args.args
        defaults = dict(
            zip(args[len(args) - len(node.args.defaults) :], node.args.defaults, strict=True)
        )
        kinds = {
            isinstance(default, ast.Name)
            for arg, default in defaults.items()
            if is_path(arg.annotation)
        }
        return len(kinds) > 1

    assert _find(is_violation) == []


def test_rules_keep_their_function_names() -> None:
    assert _find(lambda node: _has_keyword(node, _FAC_DECORATORS, "name")) == []


def test_the_output_directory_is_fac_out_with_no_argument() -> None:
    assert _find(lambda node: ast.unparse(node) == "fac.out('.')") == []


def test_directory_removal_fails_on_what_it_cannot_delete() -> None:
    assert _find(lambda node: _has_keyword(node, {"shutil.rmtree"}, "ignore_errors")) == []
