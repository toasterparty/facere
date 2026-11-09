"""Targets: names and output paths on the command line, built in the order given, or the defaults when none is given."""

from pathlib import Path

import pytest

from ..helpers import Fac


@pytest.mark.project("task_args")
def test_arguments_after_double_dash_fill_the_tasks_args_unparsed(fac: Fac) -> None:
    result = fac("echo", "--", "-q", "--out", "x")

    assert result.status == 0, result.err
    assert result.out == "-q --out x\n"


@pytest.mark.project("task_args")
def test_args_parameter_without_double_dash_holds_its_default_else_an_empty_tuple(
    fac: Fac,
) -> None:
    result = fac("greet", "echo")

    assert result.status == 0, result.err
    assert result.out == "hello\n(none)\n"


@pytest.mark.project("task_args")
def test_every_task_taking_args_receives_the_same_arguments(fac: Fac) -> None:
    result = fac("greet", "silent", "echo", "--", "a")

    assert result.status == 0, result.err
    assert result.out == "a\na\n"


@pytest.mark.project("task_args")
def test_arguments_with_a_rule_and_a_task_taking_args_pass(root: Path, fac: Fac) -> None:
    result = fac("note", "echo", "--", "a")

    assert result.status == 0, result.err
    assert result.out == "a\n"
    assert (root / "build" / "note.txt").exists()


@pytest.mark.project("task_args")
def test_arguments_with_only_rules_as_targets_fail(fac: Fac) -> None:
    result = fac("note", "--", "a")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac: error: -- passes arguments to the tasks among the targets, which name none",
    ]


@pytest.mark.project("task_args")
def test_arguments_no_task_takes_fail_naming_every_task(fac: Fac) -> None:
    result = fac("silent", "hello", "--", "a")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:19:2: error: task 'silent' takes no arguments, and -- passes some",
        "fac.py:24:2: note: task 'hello' takes none either",
    ]


@pytest.mark.project("task_args")
def test_bare_double_dash_before_a_task_taking_no_args_is_ignored(fac: Fac) -> None:
    result = fac("silent", "--")

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 1 task.\n"


@pytest.mark.project("task_args")
def test_bare_double_dash_before_a_rule_is_ignored(fac: Fac) -> None:
    result = fac("note", "--")

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("task_args")
def test_bare_double_dash_empties_the_tasks_args(fac: Fac) -> None:
    result = fac("greet", "--")

    assert result.status == 0, result.err
    assert result.out == "\n"


@pytest.mark.project("task_args")
def test_double_dash_without_targets_exits_two(fac: Fac) -> None:
    result = fac("--", "a")

    assert result.status == 2
    assert result.err.splitlines()[-1] == (
        "fac: error: -- passes arguments to the tasks among the targets, which name none"
    )


@pytest.mark.project("pages")
def test_no_targets_build_the_defaults(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 3 rules.\n"
    assert (root / "build" / "index.html").read_text() == "build/a.html build/b.html"


@pytest.mark.project("pages")
def test_name_shared_by_each_builds_every_rule_of_the_function(root: Path, fac: Fac) -> None:
    result = fac("page")

    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert sorted(path.name for path in (root / "build").glob("*.html")) == ["a.html", "b.html"]


@pytest.mark.project("definition_order")
def test_rule_executes_after_the_rule_outputting_its_input_whatever_the_definition_order(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "wrap.txt").read_text() == "[a]"


@pytest.mark.project("directory_holding_outputs")
def test_rule_inputting_a_directory_executes_after_the_rules_outputting_inside_it(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "listing.txt").read_text() == "gen.c"


@pytest.mark.project("pages")
def test_path_builds_only_the_rule_outputting_it(root: Path, fac: Fac) -> None:
    result = fac("build/b.html")

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert sorted(path.name for path in (root / "build").glob("*.html")) == ["b.html"]


@pytest.mark.project("pages")
def test_path_with_backslashes_names_the_same_output(fac: Fac) -> None:
    result = fac("build\\b.html")

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


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

    assert rebuilt.err == "Finished in <elapsed>. Executed 1 task and 3 rules.\n"
    assert cleaned.err == "Finished in <elapsed>. Executed 1 task. 3 outputs up to date.\n"
    assert not (root / "build").exists()


@pytest.mark.project("pages")
def test_unknown_target_fails_listing_the_names(root: Path, fac: Fac) -> None:
    result = fac("pages", "build/c.html")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac: error: unknown target 'pages', 'build/c.html'",
        "fac: note: names: clean, index, list, page",
    ]
    assert not (root / "build" / "index.html").exists()


@pytest.mark.project("tasks_only")
def test_tasks_stay_unexecuted_when_no_targets_and_no_defaults_leave_no_rule(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == ""
    assert result.err == "Finished in <elapsed>. No work to do.\n"


def test_an_empty_fac_py_does_nothing_successfully(root: Path, fac: Fac) -> None:
    (root / "fac.py").write_text("")

    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. No work to do.\n"
    assert sorted(path.name for path in root.iterdir()) == ["fac.py"]


@pytest.mark.project("no_default")
def test_no_targets_and_no_defaults_build_every_rule_and_no_task(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert result.out == ""
    assert (root / "build" / "a.txt").exists()
    assert (root / "build" / "b.txt").exists()


@pytest.mark.project("default_task")
def test_default_task_executes_without_targets(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == "hello\n"
