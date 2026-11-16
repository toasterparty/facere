"""Ending an invocation early: an interrupt kills every running command at once, and a graceful stop lets the rules executing finish."""

import os
import signal
import sys
from pathlib import Path

import pytest

from ..helpers import closing_line, mask_elapsed, start_fac, wait_for

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="these signals reach a process this way only on POSIX"
)


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.project("stop")
def test_graceful_stop_lets_the_rule_executing_finish_and_starts_no_other(root: Path) -> None:
    process = start_fac(root)
    wait_for(root / "build" / "started")

    process.send_signal(signal.SIGTERM)
    (root / "go").touch()
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == "Stopped after <elapsed>. Executed 1 rule.\n"
    assert not (root / "build" / "after.txt").exists()
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 1 output up to date."


@pytest.mark.project("stop")
def test_graceful_stop_passes_the_signal_to_the_command_a_task_is_running(root: Path) -> None:
    process = start_fac(root, "serve")
    command_pid = int(wait_for(root / "build" / "pid"))

    process.send_signal(signal.SIGTERM)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:29:2: note: stopped task 'serve'\nStopped after <elapsed>.\n"
    )
    assert not _is_running(command_pid)


@pytest.mark.project("two")
def test_interrupt_kills_every_running_command_and_names_one_rule_counting_the_rest(
    root: Path,
) -> None:
    process = start_fac(root, "-j2")
    command_pids = [int(wait_for(root / "build" / name)) for name in ("a.pid", "b.pid")]

    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 130, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:12:2: note: interrupted rule 'sleep' (build/a.txt), and 1 more recipe\n"
        "Interrupted after <elapsed>.\n"
    )
    assert [_is_running(pid) for pid in command_pids] == [False, False]
    assert not (root / "build" / "a.txt").exists()
    assert not (root / "build" / "b.txt").exists()


@pytest.mark.project("partial")
def test_interrupt_keeps_the_record_of_each_rule_that_finished_before_it(root: Path) -> None:
    process = start_fac(root)
    wait_for(root / "build" / "pid")

    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 130, stderr
    assert (
        closing_line(root, "quick") == "Finished in <elapsed>. No work to do. 1 output up to date."
    )
