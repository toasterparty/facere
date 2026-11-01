"""What fac prints: command output whole and unaltered, at most 3 lines of its own on success, and failures led by the command."""

from pathlib import Path

import pytest

from tests.helpers import Fac


@pytest.mark.project("echo")
def test_successful_command_output_is_printed_whole(fac: Fac) -> None:
    result = fac()

    assert result == (0, "out\n", "err\nfac: 1 executed, 0 up to date\n")


@pytest.mark.project("echo")
def test_quiet_flag_hides_successful_command_output(fac: Fac) -> None:
    result = fac("-q")

    assert result == (0, "", "fac: 1 executed, 0 up to date\n")


@pytest.mark.project("echo")
def test_quiet_argument_hides_successful_command_output(fac: Fac) -> None:
    result = fac("quiet_echo")

    assert result == (0, "", "fac: 1 executed, 0 up to date\n")


@pytest.mark.project("echo")
def test_failed_command_leads_with_the_command_and_its_output_then_names_the_rule(fac: Fac) -> None:
    result = fac("-q", "failing_echo")

    assert result.status == 1
    assert result.out == "out\n"
    lines = result.err.splitlines()
    assert lines[0].startswith("fac: command exited with status 3: ")
    assert lines[0].endswith(" echo.py 3")
    assert lines[1:] == [
        "err",
        "fac.py:18:2: error: rule 'failing_echo' (build/failing.txt) failed",
    ]


@pytest.mark.project("assertion")
def test_failed_recipe_prints_its_traceback_then_names_the_rule(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    lines = result.err.splitlines()
    assert lines[0] == "Traceback (most recent call last):"
    assert '    assert 1 + 1 == 3, "arithmetic"' in lines
    assert lines[-2:] == [
        "AssertionError: arithmetic",
        "fac.py:4:2: error: rule 'check' (build/checked.txt) failed",
    ]
    assert "_build.py" not in result.err


@pytest.mark.project("file_under_file")
def test_error_on_a_rule_path_fails_the_rule_naming_it(fac: Fac) -> None:
    result = fac("file", "nested")

    assert result.status == 1
    (line,) = result.err.splitlines()
    assert line.startswith("fac.py:9:2: error: rule 'nested' (build/x/y) failed: ")
    assert line.endswith(" 'build/x': fix the path or its permissions")


@pytest.mark.project("fail_then_touch")
def test_first_failure_stops_the_build(root: Path, fac: Fac) -> None:
    result = fac("fail", "after")

    assert result.status == 1
    assert not (root / "build" / "b.txt").exists()


@pytest.mark.project("many_rules")
def test_success_prints_at_most_three_lines_of_its_own(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == ""
    assert result.err.splitlines() == ["fac: 20 executed, 0 up to date"]
