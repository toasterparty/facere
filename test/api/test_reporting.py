"""What fac prints: command output whole and unaltered, at most 3 lines of its own on success, and failures led by the command."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import facere

from ..helpers import Fac


@pytest.mark.project("echo")
def test_successful_command_output_is_printed_whole(fac: Fac) -> None:
    result = fac()

    assert result == (0, "out\n", "err\nFinished in <elapsed>. Executed 1 rule.\n")


@pytest.mark.project("echo")
def test_quiet_flag_hides_successful_command_output(fac: Fac) -> None:
    result = fac("-q")

    assert result == (0, "", "Finished in <elapsed>. Executed 1 rule.\n")


@pytest.mark.project("echo")
def test_quiet_argument_hides_successful_command_output(fac: Fac) -> None:
    result = fac("quiet_echo")

    assert result == (0, "", "Finished in <elapsed>. Executed 1 rule.\n")


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
    assert line.endswith(" 'build/x'")


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
    assert result.err.splitlines() == ["Finished in <elapsed>. Executed 20 rules."]


@pytest.mark.project("echo")
def test_elapsed_time_names_hours_and_minutes_once_past_them(
    root: Path, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    readings = iter([0.0, 3725.3])
    monkeypatch.setattr("facere._cli.time", SimpleNamespace(perf_counter=lambda: next(readings)))
    monkeypatch.chdir(root)

    assert facere.main(["-q"]) == 0

    assert capfd.readouterr().err == "Finished in 1hr 2min 5.3s. Executed 1 rule.\n"


@pytest.mark.project("echo")
def test_elapsed_time_under_a_minute_shows_seconds_only(
    root: Path, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    readings = iter([0.0, 13.3])
    monkeypatch.setattr("facere._cli.time", SimpleNamespace(perf_counter=lambda: next(readings)))
    monkeypatch.chdir(root)

    assert facere.main(["-q"]) == 0

    assert capfd.readouterr().err == "Finished in 13.3s. Executed 1 rule.\n"


@pytest.mark.project("echo")
def test_elapsed_time_under_a_second_shows_milliseconds(
    root: Path, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    readings = iter([0.0, 0.523])
    monkeypatch.setattr("facere._cli.time", SimpleNamespace(perf_counter=lambda: next(readings)))
    monkeypatch.chdir(root)

    assert facere.main(["-q"]) == 0

    assert capfd.readouterr().err == "Finished in 523ms. Executed 1 rule.\n"
