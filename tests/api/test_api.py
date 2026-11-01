"""The rest of the fac.py interface and fac.main: exports, decorators, fac.out, minimum_version, flags, and isolation between calls."""

import sys
from pathlib import Path

import pytest

import facere
from tests.helpers import Fac


def test_all_exports_exactly_the_fac_py_interface() -> None:
    assert sorted(facere.__all__) == [
        "Input",
        "Output",
        "main",
        "minimum_version",
        "out",
        "rule",
        "run",
        "task",
    ]


@pytest.mark.project("undecorated")
def test_decorators_return_the_function_unchanged_with_or_without_parentheses(fac: Fac) -> None:
    assert fac("touch", "other").err == "fac: 2 executed, 0 up to date\n"


@pytest.mark.project("keyword_values")
def test_keyword_arguments_fill_parameters_in_every_rule_and_defaults_fill_the_rest(
    root: Path, fac: Fac
) -> None:
    fac()

    assert [(root / "build" / name).read_text() for name in ("a", "b")] == ["xx", "xx"]


@pytest.mark.project("future_annotations")
def test_annotations_resolve_under_future_annotations(fac: Fac) -> None:
    assert fac().err == "fac: 1 executed, 0 up to date\n"


@pytest.mark.project("out_paths")
def test_out_mirrors_a_path_inside_the_output_directory(fac: Fac) -> None:
    assert fac().out == "build/src/a.o build build/b build/c.h\n"


@pytest.mark.project("out_outside_root")
def test_out_keeps_a_path_inside_an_output_directory_outside_the_root(root: Path, fac: Fac) -> None:
    result = fac("--out", "../out", cwd=root / "root")

    assert result.status == 0, result.err
    assert result.out == "../out/a ../out/a\n"


@pytest.mark.project("touch")
def test_out_flag_moves_the_output_directory_and_its_last_value_wins(root: Path, fac: Fac) -> None:
    fac("--out", "first", "--out", "out/second")

    assert sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".fac" not in path.parts
    ) == ["fac.py", "out/second/a"]


@pytest.mark.project("where")
def test_directory_flag_names_the_root(root: Path, fac: Fac) -> None:
    elsewhere = root / "elsewhere"
    elsewhere.mkdir()

    result = fac("-C", "..", cwd=elsewhere)

    assert result.status == 0, result.err
    assert result.out == f"True {root.name}\n"


@pytest.mark.project("nested")
def test_missing_fac_py_fails_naming_the_nearest_ancestor_holding_one(root: Path, fac: Fac) -> None:
    result = fac(cwd=root / "src" / "lib")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac: error: no fac.py in the working directory: run fac in the directory holding the project's fac.py, or name that directory with -C",
        "fac: note: the nearest directory holding a fac.py is ../..: run fac -C ../..",
    ]


@pytest.mark.project("minimum_version_met")
def test_minimum_version_at_or_below_the_running_version_passes(fac: Fac) -> None:
    assert fac().status == 0


@pytest.mark.project("minimum_version_unmet")
def test_minimum_version_above_the_running_version_fails_naming_the_upgrade(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:3:1: error: this project needs Facere 0.1.1 or newer, and Facere 0.1.0 is running: upgrade it with `uv tool upgrade facere`",
    ]


@pytest.mark.project("minimum_version_invalid")
def test_minimum_version_that_is_not_dotted_numbers_fails_loading(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert (
        "ValueError: fac.minimum_version takes a version such as \"0.1\", not '1.x'"
        in result.err.splitlines()
    )
    assert (
        result.err.splitlines()[-1]
        == "fac.py:3:1: error: loading fac.py raised ValueError: fix the code the traceback above names"
    )


@pytest.mark.project("shared_module")
def test_shared_module_imports_from_the_root_and_leaves_no_pycache_there(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == "one\n"
    assert list(root.rglob("__pycache__")) == []
    assert sorted(
        path.name
        for path in root.rglob("*.pyc")
        if (root / "build" / ".fac" / "pycache") in path.parents
    ) == [
        f"__init__.{sys.implementation.cache_tag}.pyc",
        f"words.{sys.implementation.cache_tag}.pyc",
    ]


@pytest.mark.project("shared_module")
def test_repeated_calls_import_shared_modules_afresh(root: Path, fac: Fac) -> None:
    fac()
    # Python trusts a .pyc whose source kept its size and its mtime to the second, so the edit changes the size.
    (root / "tools" / "words.py").write_text("WORD = 'three'\n")

    assert fac().out == "three\n"


@pytest.mark.project("two_projects")
def test_repeated_calls_share_no_definitions(root: Path, fac: Fac) -> None:
    assert [fac(cwd=root / name).out for name in ("one", "two", "one")] == [
        "one\n",
        "two\n",
        "one\n",
    ]


@pytest.mark.project("imports_fac_py")
def test_importing_fac_py_fails_naming_the_fix(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert (
        "error: fac.py ran a second time because a module imported it: move what you share into a shared module"
        in result.err
    )
