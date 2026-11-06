"""Each project in the directory named after a test module is copied by a test in that module, and each project a test names exists there."""

import ast
from pathlib import Path

TESTS = Path(__file__).parent
MODULES = sorted(path for path in TESTS.rglob("test_*.py") if path != Path(__file__))


def _find_named_projects(module: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and ast.unparse(decorator.func) == "pytest.mark.project"
            ):
                continue
            (name,) = decorator.args
            assert isinstance(name, ast.Constant) and isinstance(name.value, str), (
                f"{module.name}:{decorator.lineno} names its project with a non-literal"
            )
            names.add(name.value)
    return names


def _find_projects(module: Path) -> set[str]:
    directory = module.with_suffix("")
    if not directory.is_dir():
        return set()
    return {
        path.name for path in directory.iterdir() if path.is_dir() and path.name != "__pycache__"
    }


def _label(module: Path, name: str) -> str:
    return f"{module.relative_to(TESTS).with_suffix('').as_posix()}/{name}"


def test_every_project_is_named_by_a_test_in_its_module() -> None:
    unnamed = {
        _label(module, name)
        for module in MODULES
        for name in _find_projects(module) - _find_named_projects(module)
    }

    assert unnamed == set()


def test_every_project_a_test_names_exists() -> None:
    missing = {
        _label(module, name)
        for module in MODULES
        for name in _find_named_projects(module) - _find_projects(module)
    }

    assert missing == set()


def test_every_project_directory_belongs_to_a_test_module() -> None:
    packages = [TESTS, *(path.parent for path in TESTS.rglob("__init__.py"))]
    strays = {
        path.relative_to(TESTS).as_posix()
        for package in packages
        for path in package.glob("test_*")
        if path.is_dir() and not path.with_suffix(".py").is_file()
    }

    assert strays == set()
