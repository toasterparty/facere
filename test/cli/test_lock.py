"""The lock on an output directory: a second invocation waits for the first, which a task that keeps running lets in through fac.give_lock."""

import sys
from pathlib import Path

import pytest

from facere._lock import OutputLock

from ..helpers import mask_elapsed, run_fac, start_fac, wait_for


def _read_holder(root: Path) -> int:
    """Return the PID the holding invocation wrote, which on Windows is not that of the process `start_fac` started, since a uv environment's python.exe is a launcher running the interpreter as its child."""
    return int((root / "build" / ".fac" / "lock.pid").read_text())


@pytest.mark.project("hold")
def test_second_invocation_names_the_first_and_builds_once_it_ends(root: Path) -> None:
    first = start_fac(root)
    wait_for(root / "build" / "holding")
    holder = _read_holder(root)
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
        f"fac: note: waiting for the invocation with PID {holder}, which holds the output directory build\n"
    )
    assert mask_elapsed(second_err) == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("hold")
def test_lock_timeout_fails_with_status_three_once_it_runs_out(root: Path) -> None:
    first = start_fac(root)
    wait_for(root / "build" / "holding")
    holder = _read_holder(root)

    result = run_fac(root, "--lock-timeout", "0", "quick")
    (root / "go").touch()
    first.communicate(timeout=30)

    assert result.status == 3
    assert result.err == (
        f"fac: error: the invocation with PID {holder} still held the output directory build after 0 seconds\n"
        "Failed after <elapsed>.\n"
    )


@pytest.mark.skipif(
    sys.platform != "win32", reason="on Windows killing the holder abandons its named mutex"
)
@pytest.mark.project("hold")
def test_lock_whose_holder_was_killed_is_taken_by_the_next_invocation(root: Path) -> None:
    assert sys.platform == "win32"
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    first = start_fac(root)
    wait_for(root / "build" / "holding")
    key = OutputLock("build", str(root / "build" / ".fac"))._key
    # A second handle keeps the mutex alive once its holder dies, as a waiter's does, so the next invocation finds it abandoned.
    mutex = kernel32.OpenMutexW(synchronize, False, f"Local\\facere-{key}")
    assert mutex, ctypes.get_last_error()
    try:
        first.kill()
        first.communicate(timeout=30)
        result = run_fac(root, "--lock-timeout", "5", "give_then_nest")
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(mutex))

    assert result.err == (
        "Finished in <elapsed>. Executed 1 rule.\nFinished in <elapsed>. Executed 1 task.\n"
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
