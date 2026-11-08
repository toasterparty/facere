"""A rule's recipe fails on using a file under the root, or a path a rule outputs, that it doesn't declare."""

from pathlib import Path

import pytest

from ..helpers import Fac, edit

EXECUTED_ONE = "Finished in <elapsed>. Executed 1 rule.\n"


def _error(line: str, action: str, path: str) -> str:
    return f"fac.py:{line}: error: rule 'use' (build/result.txt) failed: its recipe {action} {path}, which no fac.Input parameter declares"


@pytest.mark.project("command")
def test_argument_naming_an_undeclared_file_fails_before_the_command_runs(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 1
    assert result.err == _error("6:2", "gave a command", "tool.cfg") + "\n"
    assert not (root / "build" / "result.txt").exists()


@pytest.mark.project("command")
def test_flag_parts_split_at_equals_and_comma_are_checked(root: Path, fac: Fac) -> None:
    edit(root / "fac.py", '"tool.cfg"', '"-Wl,-Map=tool.cfg"')

    result = fac()

    assert result.status == 1
    assert result.err == _error("6:2", "gave a command", "tool.cfg") + "\n"


@pytest.mark.project("command")
def test_relative_argument_resolves_against_cwd(root: Path, fac: Fac) -> None:
    edit(root / "fac.py", '"tool.cfg"', '"near.cfg"')
    edit(root / "fac.py", "cwd=None", 'cwd="sub"')

    result = fac()

    assert result.status == 1
    assert result.err == _error("6:2", "gave a command", "sub/near.cfg") + "\n"


@pytest.mark.project("command")
def test_argument_resolving_to_nothing_under_cwd_passes(root: Path, fac: Fac) -> None:
    edit(root / "fac.py", "cwd=None", 'cwd="sub"')

    assert fac().err == EXECUTED_ONE


@pytest.mark.project("declared")
def test_declared_input_may_be_passed_and_opened(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE


@pytest.mark.project("directory_input")
def test_file_inside_a_declared_directory_counts_as_declared(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE


@pytest.mark.project("program")
def test_program_under_the_root_must_be_declared(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err == _error("4:2", "ran", "tools/run.py") + "\n"


@pytest.mark.project("unbuilt_tool")
def test_running_another_rules_output_names_that_rule_rather_than_a_missing_file(fac: Fac) -> None:
    result = fac("use")

    assert result.status == 1
    assert result.err.splitlines() == [
        _error("11:2", "ran", "build/tool"),
        "fac.py:6:2: note: rule 'build_tool' (build/tool) outputs build/tool",
    ]


@pytest.mark.project("data_value")
def test_path_a_str_parameter_holds_is_exempt(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE


@pytest.mark.project("shared_module")
def test_recipe_may_open_a_shared_module(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE


@pytest.mark.project("shared_module")
def test_command_given_a_shared_module_fails_since_no_fingerprint_holds_it(
    root: Path, fac: Fac
) -> None:
    edit(
        root / "fac.py",
        'fac.read_text("helpers_shared.py")',
        'fac.run("python3", "helpers_shared.py")',
    )

    result = fac()

    assert result.status == 1
    assert result.err == _error("6:2", "gave a command", "helpers_shared.py") + "\n"


@pytest.mark.project("exempt")
def test_scratch_hidden_absent_and_self_written_files_are_exempt(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == EXECUTED_ONE


@pytest.mark.project("opened")
def test_opening_an_undeclared_file_fails(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err == _error("4:2", "opened", "tool.cfg") + "\n"


@pytest.mark.project("swallowed")
def test_except_exception_cannot_hide_the_failure(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err == _error("6:2", "opened", "tool.cfg") + "\n"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
@pytest.mark.project("command_in_thread")
def test_command_from_a_thread_the_recipe_starts_still_fails_the_rule(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err.splitlines()[-1] == _error("7:2", "gave a command", "tool.cfg")


@pytest.mark.project("report_first")
def test_file_reported_before_opening_it_is_tracked_instead(root: Path, fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE

    (root / "tool.cfg").write_text("edited")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "result.txt").read_text() == "edited"


@pytest.mark.project("other_output")
def test_opening_another_rules_output_names_that_rule(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        _error("9:2", "opened", "build/made.txt"),
        "fac.py:4:2: note: rule 'make' (build/made.txt) outputs build/made.txt",
    ]


@pytest.mark.project("task_unchecked")
def test_a_task_goes_unchecked(fac: Fac) -> None:
    result = fac("show")

    assert result.status == 0, result.err
    assert result.out == "cfg\n"


@pytest.mark.project("collection_read")
def test_reading_a_file_while_fac_py_loads_goes_unchecked(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE
    assert fac().status == 0
