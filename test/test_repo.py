"""Facts that several repository files must each spell out, since none of those formats can import another."""

import ast
import json
import re
import tomllib
from typing import Any

import pytest

from .helpers import REPO, load_module

pytestmark = pytest.mark.skipif(
    not (REPO / ".github").is_dir(), reason="an sdist holds no repository config"
)

_TARGET_DECORATORS = {"fac.rule", "fac.task"}


def _read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def _find_root_targets() -> set[str]:
    def is_target(decorator: ast.expr) -> bool:
        callee = decorator.func if isinstance(decorator, ast.Call) else decorator
        return ast.unparse(callee) in _TARGET_DECORATORS

    return {
        node.name.rstrip("_")
        for node in ast.parse(_read("fac.py")).body
        if isinstance(node, ast.FunctionDef) and any(map(is_target, node.decorator_list))
    }


def _read_pyproject() -> dict[str, Any]:
    return tomllib.loads(_read("pyproject.toml"))


def test_ci_covers_the_oldest_python_and_the_one_development_uses() -> None:
    match = re.search(r'^ +python: \["(.+)", "(.+)"\]$', _read(".github/workflows/ci.yml"), re.M)
    assert match is not None

    assert f">={match[1]}" == _read_pyproject()["project"]["requires-python"]
    assert match[2] == _read(".python-version").strip()


def test_release_workflow_offers_each_release_type() -> None:
    match = re.search(r"^ +options: \[(.+)\]$", _read(".github/workflows/release.yml"), re.M)
    assert match is not None

    assert tuple(match[1].split(", ")) == load_module(REPO / "release.py").CHOICES


def test_setup_action_extracts_a_version_from_the_root_fac_py() -> None:
    assert r's/^MINIMUM_FACERE = "\(.*\)"$/\1/p' in _read(".github/actions/setup-fac/action.yml")
    assert re.search(r'^MINIMUM_FACERE = "\d+\.\d+\.\d+"$', _read("fac.py"), re.M) is not None


def test_workflows_run_only_targets_the_root_fac_py_defines() -> None:
    workflows = _read(".github/workflows/ci.yml") + _read(".github/workflows/release.yml")

    ran = set(re.findall(r"run: (?:uvx facere|fac) (\w+)", workflows))

    assert ran >= {"ci", "build_release", "push_release", "publish_release"}
    assert ran <= _find_root_targets()


def test_vscode_tasks_run_the_targets_they_are_labelled_with() -> None:
    tasks = json.loads(_read(".vscode/tasks.json"))["tasks"]

    assert all(task["command"] == f"fac {task['label']}" for task in tasks)
    assert {task["label"] for task in tasks} <= _find_root_targets()


def test_development_guide_lists_each_target() -> None:
    listed = re.findall(r"^\| `(\w+)` \|", _read("doc/maintainer/development.md"), re.M)

    assert set(listed) == _find_root_targets()


def test_ruff_and_ty_skip_exactly_the_planned_examples() -> None:
    pyproject = _read_pyproject()
    ruff_skips = set(pyproject["tool"]["ruff"]["extend-exclude"])
    ty_skips = set(pyproject["tool"]["ty"]["src"]["exclude"])
    planned = re.findall(r"\[`([\w-]+)/`\]\(.*\) \*\(planned\)\*", _read("doc/examples/README.md"))

    assert ruff_skips == ty_skips
    assert {skip.split("/")[2] for skip in ruff_skips} == set(planned)


def test_hatch_reads_the_version_from_the_file_a_release_rewrites() -> None:
    match = re.search(r'^VERSION_FILE = "(.+)"$', _read("fac.py"), re.M)
    assert match is not None

    assert match[1] == _read_pyproject()["tool"]["hatch"]["version"]["path"]
