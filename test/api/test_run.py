"""fac.run: one command without a shell, its program resolved before spawning, its streams redirected to files on request."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ..helpers import Fac, run_fac


@pytest.mark.project("answer")
def test_run_returns_the_command_stdout(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "answer.txt").read_text() == "42"


@pytest.mark.project("sequences")
def test_list_or_tuple_argument_passes_each_item_as_one_argument(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "argv.txt").read_text() == "a b c d"


@pytest.mark.project("nested_sequence")
def test_list_nested_in_a_list_argument_fails_the_recipe(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert (
        "TypeError: fac.run takes the program and its arguments as strings, or lists or tuples of strings, not ('python', [['-V']])"
        in result.err.splitlines()
    )


@pytest.mark.project("stdin")
def test_rule_command_reads_an_empty_stdin_unless_stdin_names_a_file(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "fed.txt").read_text() == "'' 'fed'"


@pytest.mark.project("redirect")
def test_stdout_and_stderr_fill_the_files_they_name(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == ""
    assert (root / "build" / "o.txt").read_text() == "o"
    assert (root / "build" / "e.txt").read_text() == "e"
    assert sorted((root / "build" / "both.txt").read_text()) == ["e", "o"]


@pytest.mark.project("redirect")
def test_stderr_alone_fills_its_file_and_stdout_is_still_printed(root: Path, fac: Fac) -> None:
    result = fac("err_only")

    assert result.status == 0, result.err
    assert result.out == "o"
    assert (root / "build" / "err_only.txt").read_text() == "e"


@pytest.mark.project("redirect_spelling")
def test_stdout_and_stderr_spelling_one_file_differently_both_fill_it(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert sorted((root / "build" / "both.txt").read_text()) == ["e", "o"]


@pytest.mark.project("env")
def test_env_sets_variables_over_the_inherited_environment_and_none_unsets_one(
    root: Path, fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACERE_TEST_INHERITED", "inherited")
    monkeypatch.setenv("FACERE_TEST_UNSET", "unset")

    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "env.txt").read_text() == "inherited set None"


@pytest.mark.project("project_env")
def test_project_env_sets_variables_for_every_command_under_each_commands_env(
    root: Path, fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACERE_TEST_INHERITED", "inherited")
    monkeypatch.setenv("FACERE_TEST_UNSET", "unset")

    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "env.txt").read_text() == "inherited project None command"


@pytest.mark.project("env_repeated")
def test_project_env_may_repeat_a_variables_value(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "locale.txt").read_text() == "C UTC"


@pytest.mark.project("env_conflict")
def test_project_env_changing_a_variables_value_fails_naming_both_calls(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:1: error: fac.env sets LC_ALL to 'C.UTF-8', though another call set it to 'C'",
        "fac.py:3:1: note: fac.env sets LC_ALL here",
    ]


@pytest.mark.project("env_in_recipe")
def test_project_env_in_a_recipe_fails_it(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert (
        "RuntimeError: fac.env works only while fac.py loads, since a recipe that calls it reads what no fingerprint holds"
        in result.err.splitlines()
    )


@pytest.mark.skipif(sys.platform == "win32", reason="a shell script is a program only on POSIX")
@pytest.mark.project("separator")
def test_program_with_a_separator_resolves_against_the_root_whatever_cwd_is(
    root: Path, fac: Fac
) -> None:
    os.chmod(root / "tools" / "greet", 0o755)

    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "greeting.txt").read_text() == "hello from sub"


@pytest.mark.project("missing_program")
def test_program_that_does_not_resolve_fails_the_recipe_naming_it(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert (
        "FileNotFoundError: [Errno 2] fac.run found no program 'facere-no-such-program' on PATH: 'facere-no-such-program'"
        in result.err.splitlines()
    )


@pytest.mark.skipif(sys.platform == "win32", reason="sessions are POSIX")
@pytest.mark.project("session")
def test_rule_command_runs_in_a_session_of_its_own(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "session.txt").read_text() == "True"


@pytest.mark.project("timeout")
def test_timeout_failure_names_the_limit_set_not_the_time_remaining(
    fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    communicate = subprocess.Popen.communicate
    calls = []

    def expire_once(self: subprocess.Popen[bytes], *args: object, **kwargs: object) -> object:
        calls.append(None)
        if len(calls) == 1:
            # Python 3.11 reports the time remaining when the command has no pipes.
            raise subprocess.TimeoutExpired(self.args, 0.25)
        return communicate(self)

    monkeypatch.setattr(subprocess.Popen, "communicate", expire_once)

    result = fac()

    assert result.status == 1
    assert result.err.splitlines()[0].startswith("fac: command timed out after 1 seconds: ")


@pytest.mark.project("task")
def test_task_command_shares_facere_streams_so_run_returns_nothing(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == "hello\n"


@pytest.mark.project("task_quiet")
def test_quiet_task_command_returns_its_stdout_without_printing_it(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == "read 42\n"


@pytest.mark.skipif(sys.platform == "win32", reason="sessions are POSIX")
@pytest.mark.project("task_quiet_session")
def test_quiet_task_command_runs_in_a_session_a_timeout_can_kill_whole(fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.out == "True\n"


@pytest.mark.project("task_quiet_stdin")
def test_quiet_task_command_ignores_typed_stdin_unless_stdin_names_a_file(root: Path) -> None:
    result = run_fac(root, stdin_text="typed")

    assert result.status == 0, result.err
    assert result.out == "'' 'fed'\n"


@pytest.mark.project("task_quiet_failure")
def test_quiet_task_command_that_fails_shows_the_output_it_hid(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert "from stdout\n" in result.out
    assert "from stderr\n" in result.err


@pytest.mark.project("outside_recipe")
def test_run_outside_a_recipe_fails_collection(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert (
        "RuntimeError: fac.run runs a command only from the recipe of a rule or task"
        in result.err.splitlines()
    )
