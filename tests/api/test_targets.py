"""Targets: names and output paths on the command line, built in the order given, or the defaults when none is given."""

from pathlib import Path

import pytest

from tests.helpers import Fac


@pytest.mark.project("pages")
def test_no_targets_build_the_defaults(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "fac: 3 executed, 0 up to date\n"
    assert (root / "build" / "index.html").read_text() == "build/a.html build/b.html"


@pytest.mark.project("pages")
def test_name_shared_by_each_builds_every_rule_of_the_function(root: Path, fac: Fac) -> None:
    result = fac("page")

    assert result.err == "fac: 2 executed, 0 up to date\n"
    assert sorted(path.name for path in (root / "build").glob("*.html")) == ["a.html", "b.html"]


@pytest.mark.project("definition_order")
def test_rule_executes_after_the_rule_outputting_its_input_whatever_the_definition_order(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "fac: 2 executed, 0 up to date\n"
    assert (root / "build" / "wrap.txt").read_text() == "[a]"


@pytest.mark.project("pages")
def test_path_builds_only_the_rule_outputting_it(root: Path, fac: Fac) -> None:
    result = fac("build/b.html")

    assert result.err == "fac: 1 executed, 0 up to date\n"
    assert sorted(path.name for path in (root / "build").glob("*.html")) == ["b.html"]


@pytest.mark.project("pages")
def test_path_with_backslashes_names_the_same_output(fac: Fac) -> None:
    result = fac("build\\b.html")

    assert result.err == "fac: 1 executed, 0 up to date\n"


@pytest.mark.project("pages")
def test_function_name_loses_one_trailing_underscore_and_name_replaces_it(fac: Fac) -> None:
    result = fac("list")

    assert result.status == 0, result.err
    assert result.out == "build/a.html build/b.html\n"


@pytest.mark.project("pages")
def test_targets_build_in_the_order_given(root: Path, fac: Fac) -> None:
    fac()

    rebuilt = fac("clean", "index")
    cleaned = fac("index", "clean")

    assert rebuilt.err == "fac: 4 executed, 0 up to date\n"
    assert cleaned.err == "fac: 1 executed, 3 up to date\n"
    assert not (root / "build").exists()


@pytest.mark.project("pages")
def test_unknown_target_fails_listing_the_names(root: Path, fac: Fac) -> None:
    result = fac("pages", "build/c.html")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac: error: unknown target 'pages', 'build/c.html': name a rule or task, or give the path a rule outputs, relative to the root",
        "fac: note: names: clean, index, list, page",
    ]
    assert not (root / "build" / "index.html").exists()


@pytest.mark.project("no_default")
def test_no_targets_and_no_defaults_fail_listing_the_names(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac: error: fac.py declares no default, so name a target, or pass default=True to fac.rule or fac.task",
        "fac: note: names: hello",
    ]


@pytest.mark.project("default_task")
def test_default_task_executes_without_targets(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == "hello\n"
