"""The lock on an output directory: a second invocation waits for the first, which a task that keeps running lets in through fac.give_lock."""

from pathlib import Path

import pytest

from ..helpers import mask_elapsed, run_fac, start_fac, wait_for


@pytest.mark.project("hold")
def test_second_invocation_names_the_first_and_builds_once_it_ends(root: Path) -> None:
    first = start_fac(root)
    wait_for(root / "build" / "holding")
    second = start_fac(root, "quick")
    assert second.stderr is not None
    waiting = second.stderr.readline()
    assert not (root / "build" / "quick.txt").exists()
    assert (root / "loads.txt").read_text() == "loaded\n"

    (root / "go").touch()
    _, first_err = first.communicate(timeout=30)
    second_err = second.stderr.read()

    assert first.returncode == 0, first_err
    assert second.wait(timeout=30) == 0, second_err
    assert waiting == (
        f"fac: note: waiting for the invocation with PID {first.pid}, which holds the output directory build\n"
    )
    assert mask_elapsed(second_err) == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("hold")
def test_lock_timeout_fails_with_status_three_once_it_runs_out(root: Path) -> None:
    first = start_fac(root)
    wait_for(root / "build" / "holding")

    result = run_fac(root, "--lock-timeout", "0", "quick")
    (root / "go").touch()
    first.communicate(timeout=30)

    assert result.status == 3
    assert result.err == (
        f"fac: error: the invocation with PID {first.pid} still held the output directory build after 0 seconds\n"
        "Failed after <elapsed>.\n"
    )


@pytest.mark.project("hold")
def test_invocation_on_another_output_directory_does_not_wait(root: Path) -> None:
    first = start_fac(root)
    wait_for(root / "build" / "holding")

    result = run_fac(root, "--out", "build2", "quick")
    (root / "go").touch()
    first.communicate(timeout=30)

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("hold")
def test_recipe_running_fac_on_the_output_directory_its_invocation_holds_fails_at_once(
    root: Path,
) -> None:
    result = run_fac(root, "nested")

    assert result.status == 1
    lines = result.err.splitlines()
    assert lines[0].startswith("fac: error: the invocation with PID ")
    assert lines[0].endswith(
        ", which started this one, holds the output directory build, so waiting for it would never end"
    )
    assert lines[1] == "Failed after <elapsed>."
    assert lines[-1] == "Failed after <elapsed>."


@pytest.mark.project("hold")
def test_recipe_running_fac_on_another_output_directory_builds(root: Path) -> None:
    result = run_fac(root, "nested_elsewhere")

    assert result.status == 0, result.err
    assert (root / "build2" / "quick.txt").read_text() == "quick"


@pytest.mark.project("given")
def test_task_that_gave_the_lock_lets_another_invocation_build(root: Path) -> None:
    result = run_fac(root, "serve")

    assert result.err == (
        "Finished in <elapsed>. Executed 1 rule.\nFinished in <elapsed>. Executed 1 task.\n"
    )


@pytest.mark.project("given")
def test_lock_a_task_gave_is_taken_again_for_the_targets_after_it(root: Path) -> None:
    result = run_fac(root, "give", "quick")

    assert result.err == "Finished in <elapsed>. Executed 1 task and 1 rule.\n"
    assert (
        run_fac(root, "quick").err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"
    )


@pytest.mark.project("given")
def test_rule_asking_for_the_lock_to_be_given_fails(root: Path) -> None:
    result = run_fac(root, "greedy")

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: fac.give_lock works only in the recipe of a task, since recording a rule needs the lock",
        "fac.py:16:2: error: rule 'greedy' (build/greedy.txt) failed",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("given")
def test_lock_is_kept_where_an_output_changed_after_its_rule_finished(root: Path) -> None:
    result = run_fac(root, "tamper_then_give")

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: fac.give_lock keeps the lock, since rule 'copy' (build/a.txt) failed: its output build/a.txt changed after it finished",
        "fac.py:34:2: error: task 'tamper_then_give' failed",
        "Failed after <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("given")
def test_invocation_removes_the_file_naming_it_as_the_lock_holder(root: Path) -> None:
    assert run_fac(root, "quick").status == 0

    assert not (root / "build" / ".fac" / "lock.pid").exists()
