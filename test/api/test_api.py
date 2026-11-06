"""The rest of the fac.py interface and fac.main: exports, decorators, fac.out, minimum_version, flags, and isolation between calls."""

import os
import sys
from pathlib import Path

import pytest

import facere

from ..helpers import Fac


def test_all_exports_exactly_the_fac_py_interface() -> None:
    assert sorted(facere.__all__) == [
        "Args",
        "Input",
        "Output",
        "env",
        "main",
        "minimum_version",
        "out",
        "read_text",
        "rule",
        "run",
        "sources",
        "task",
        "write_text",
    ]


@pytest.mark.project("undecorated")
def test_decorators_return_the_function_unchanged_with_or_without_parentheses(fac: Fac) -> None:
    assert fac("touch", "other").err == "Finished in <elapsed>. Executed 2 rules.\n"


@pytest.mark.project("keyword_values")
def test_keyword_arguments_fill_parameters_in_every_rule_and_defaults_fill_the_rest(
    root: Path, fac: Fac
) -> None:
    fac()

    assert [(root / "build" / name).read_text() for name in ("a", "b")] == ["xx", "xx"]


@pytest.mark.project("future_annotations")
def test_annotations_resolve_under_future_annotations(fac: Fac) -> None:
    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("out_paths")
def test_out_mirrors_a_path_inside_the_output_directory(fac: Fac) -> None:
    assert fac().out == "build/src/a.o build build/b build/c.h\n"


@pytest.mark.project("text_files")
def test_text_files_read_and_write_as_utf_8_with_lf_line_endings(root: Path, fac: Fac) -> None:
    fac()

    assert (root / "build" / "target.txt").read_bytes() == b"NA\xc3\x8fVE\nLINE\n"


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


@pytest.mark.project("touch")
def test_out_flag_naming_the_root_fails(root: Path, fac: Fac) -> None:
    result = fac("--out", "./")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac: error: --out names the root, where outputs would mix with sources",
    ]
    assert not (root / ".fac").exists()


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

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac: error: no fac.py in the working directory",
        "fac: note: the nearest directory holding a fac.py is ../..",
    ]


@pytest.mark.project("minimum_version_met")
def test_minimum_version_at_or_below_the_running_version_passes(fac: Fac) -> None:
    assert fac().status == 0


@pytest.mark.project("minimum_version_unmet")
def test_minimum_version_above_the_running_version_fails_naming_the_upgrade(
    fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("facere._api.VERSION", "0.1.0")

    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:3:1: error: this project needs Facere 999.0 or newer. Detected 0.1: run `uv tool upgrade facere`",
    ]


@pytest.mark.project("minimum_version_patch")
def test_minimum_version_shows_the_patch_where_only_it_tells_the_versions_apart(
    fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("facere._api.VERSION", "0.2.0")

    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:3:1: error: this project needs Facere 0.2.1 or newer. Detected 0.2.0: run `uv tool upgrade facere`",
    ]


@pytest.mark.project("minimum_version_invalid")
def test_minimum_version_that_is_not_dotted_numbers_fails_loading(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert (
        "ValueError: fac.minimum_version takes a version such as \"0.1\", not '1.x'"
        in result.err.splitlines()
    )
    assert result.err.splitlines()[-1] == "fac.py:3:1: error: loading fac.py raised ValueError"


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
def test_importing_fac_py_fails_saying_it_ran_twice(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:6:2: error: fac.py ran a second time because a module imported it",
    ]


@pytest.mark.project("imports_other_fac_py")
def test_importing_another_projects_fac_py_fails_naming_its_definitions(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:1:1: error: this definition comes from another project's fac.py, which a module imported",
        "other/fac.py:4:2: note: declared here",
    ]


@pytest.mark.project("shadowed_import")
def test_import_shadowed_by_an_earlier_sys_path_entry_fails_naming_both_modules(
    root: Path, fac: Fac, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "facere_test_words.py").write_text('WORD = "elsewhere"\n')
    monkeypatch.syspath_prepend(str(elsewhere))
    monkeypatch.delitem(sys.modules, "facere_test_words", raising=False)

    try:
        result = fac()
    finally:
        sys.modules.pop("facere_test_words", None)

    shadow = os.path.relpath(elsewhere / "facere_test_words.py", root).replace(os.sep, "/")
    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:1:1: error: import facere_test_words resolves outside the root, though the root holds facere_test_words.py, since an earlier sys.path entry shadows facere_test_words.py",
        f"{shadow}:1:1: note: facere_test_words resolves here",
    ]


@pytest.mark.project("shadowed_by_built_in")
def test_import_shadowed_by_a_built_in_module_fails(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:1:1: error: import sys resolves to a built-in module, though the root holds sys.py, since an earlier sys.path entry shadows sys.py",
    ]


@pytest.mark.project("sources")
def test_sources_globs_sorted_files_skipping_hidden_ones_and_the_output_directory(
    root: Path, fac: Fac
) -> None:
    (root / "build").mkdir()
    (root / "build" / "d.c").write_text("x")

    result = fac()

    assert result.status == 0, result.err
    assert result.out == "['notes.txt', 'src/.dir/c.c', 'src/a.c', 'src/sub/b.c']\n"


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows separates paths with \\")
@pytest.mark.project("sources_backslash")
def test_sources_glob_with_backslashes_lists_nothing_outside_the_root(root: Path, fac: Fac) -> None:
    result = fac(cwd=root / "root")

    assert result.status == 0, result.err
    assert result.out == "[]\n"


@pytest.mark.project("sources_outside_root")
def test_sources_glob_reaching_outside_the_root_fails_loading(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert "ValueError: fac.sources takes globs under the root, not '../*.c'" in result.err
    assert result.err.splitlines()[-1] == "fac.py:3:1: error: loading fac.py raised ValueError"
