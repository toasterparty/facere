"""The status row pinned to the bottom of a terminal."""

import os
import signal
import sys
import time
from pathlib import Path

import pytest

from ..helpers import mask_elapsed
from .terminal import read_all, start_on_terminal

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the row needs a POSIX terminal")

SCROLL_REGION = "\x1b7\x1b[1;9r\x1b8\x1b[1A"
CLEAR_ROW = "\x1b7\x1b[10;1H\x1b[2K"


@pytest.mark.project("touch")
def test_row_shows_each_executing_rule_below_a_scroll_region_and_is_erased_at_the_end(
    root: Path,
) -> None:
    process, master = start_on_terminal(root)

    output = mask_elapsed(read_all(master))

    assert process.wait(timeout=30) == 0
    assert output == (
        f"\r\n{SCROLL_REGION}"
        f"{CLEAR_ROW}[1/1] rule 'touch' (build/a.txt)\x1b8"
        f"{CLEAR_ROW}\x1b[r\x1b8"
        "Finished in <elapsed>. Executed 1 rule.\r\n"
    )


@pytest.mark.project("chain")
def test_position_counts_each_rule_reached_once_per_batch_that_a_task_ends(root: Path) -> None:
    process, master = start_on_terminal(root, "second", "second", "between", "second")

    output = mask_elapsed(read_all(master))

    assert process.wait(timeout=30) == 0
    assert output == (
        f"\r\n{SCROLL_REGION}"
        f"{CLEAR_ROW}[1/5] rule 'first' (build/a.txt)\x1b8"
        f"{CLEAR_ROW}[2/5] rule 'second' (build/b.txt)\x1b8"
        f"{CLEAR_ROW}[3/5] task 'between'\x1b8"
        f"{CLEAR_ROW}\x1b[r\x1b8"
        "Finished in <elapsed>. Executed 1 task and 2 rules. 2 outputs up to date.\r\n"
    )


@pytest.mark.project("interrupt")
def test_hangup_kills_the_command_and_restores_the_scroll_region_before_the_process_dies(
    root: Path,
) -> None:
    assert sys.platform != "win32"
    (root / "block").touch()
    process, master = start_on_terminal(root)
    pid_file = root / "build" / "pid"
    deadline = time.monotonic() + 30
    while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
        time.sleep(0.05)
    command_pid = int(pid_file.read_text())

    process.send_signal(signal.SIGHUP)
    output = mask_elapsed(read_all(master))

    assert process.wait(timeout=30) == -signal.SIGHUP
    assert output.endswith(
        f"{CLEAR_ROW}\x1b[r\x1b8"
        "fac.py:8:2: note: interrupted rule 'slow' (build/a.txt)\r\n"
        "Interrupted after <elapsed>.\r\n"
    )
    with pytest.raises(ProcessLookupError):
        os.kill(command_pid, 0)
