"""Ending an invocation early: an interrupt kills every running command at once, and a graceful stop lets the rules executing finish."""

import signal
import subprocess
import sys
from pathlib import Path

import pytest

from ..helpers import (
    closing_line,
    is_running,
    mask_elapsed,
    run_in_new_console,
    start_fac,
    wait_for,
)

_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="these signals reach a process this way only on POSIX"
)
_WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="console control events exist only on Windows"
)

# Started in a console of its own, so its Ctrl-C reaches Facere and the commands Facere shares a console with, never the
# test runner. A child inherits whether Ctrl-C is ignored, so it turns Ctrl-C on before starting Facere, since Git Bash,
# as in CI, starts native programs with it off, and ignores it only once Facere has started.
_CTRL_C_DRIVER = """
import ctypes, json, subprocess, sys, time
from pathlib import Path

root, report = Path(sys.argv[1]), Path(sys.argv[2])
kernel32 = ctypes.windll.kernel32
assert kernel32.SetConsoleCtrlHandler(None, False)
fac = subprocess.Popen(
    [sys.executable, "-m", "facere", "-j2"], cwd=root, stderr=subprocess.PIPE, text=True
)
deadline = time.monotonic() + 30
pid_files = [root / "build" / name for name in ("a.pid", "b.pid")]
while not all(path.exists() and path.read_text() for path in pid_files):
    assert time.monotonic() < deadline, "the commands never started"
    time.sleep(0.01)
assert kernel32.SetConsoleCtrlHandler(None, True)
assert kernel32.GenerateConsoleCtrlEvent(0, 0)
_, stderr = fac.communicate(timeout=30)
report.write_text(json.dumps({"status": fac.returncode, "stderr": stderr}))
"""

# Facere gets the console as its stdin and stderr, which a rule's live command needs. With `break`, it starts Facere in
# a process group of its own and sends CTRL_BREAK_EVENT to that group alone, as a parent stopping it does, then lets the
# command finish. Otherwise it sends Ctrl-C to the whole console, as the keyboard does.
_LIVE_DRIVER = """
import ctypes, json, signal, subprocess, sys, time
from pathlib import Path

root, how, report = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
kernel32 = ctypes.windll.kernel32
assert kernel32.SetConsoleCtrlHandler(None, False)
with open("CONIN$") as console_in, open("CONOUT$", "w") as console_out:
    fac = subprocess.Popen(
        [sys.executable, "-m", "facere"],
        cwd=root,
        stdin=console_in,
        stderr=console_out,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if how == "break" else 0,
    )
pid_file = root / "build" / "pid"
deadline = time.monotonic() + 30
while not (pid_file.exists() and pid_file.read_text()):
    assert time.monotonic() < deadline, "the command never started"
    time.sleep(0.01)
if how == "break":
    fac.send_signal(signal.CTRL_BREAK_EVENT)
    (root / "go").touch()
else:
    assert kernel32.SetConsoleCtrlHandler(None, True)
    assert kernel32.GenerateConsoleCtrlEvent(0, 0)
report.write_text(json.dumps({"status": fac.wait(30)}))
"""


def _start_fac_in_group(root: Path, *args: str) -> subprocess.Popen[str]:
    """Start `python -m facere ARGS...` in `root` in a process group of its own, so CTRL_BREAK_EVENT reaches it and no test runner."""
    assert sys.platform == "win32"
    return subprocess.Popen(
        [sys.executable, "-m", "facere", *args],
        cwd=root,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def _send_ctrl_break(process: subprocess.Popen[str]) -> None:
    assert sys.platform == "win32"
    process.send_signal(signal.CTRL_BREAK_EVENT)


@_POSIX_ONLY
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


@_POSIX_ONLY
@pytest.mark.project("stop")
def test_graceful_stop_passes_the_signal_to_the_command_a_taskis_running(root: Path) -> None:
    process = start_fac(root, "serve")
    command_pid = int(wait_for(root / "build" / "pid"))

    process.send_signal(signal.SIGTERM)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:29:2: note: stopped task 'serve'\nStopped after <elapsed>.\n"
    )
    assert not is_running(command_pid)


@_POSIX_ONLY
@pytest.mark.project("stop")
def test_graceful_stop_passes_the_signal_to_the_session_of_a_command_a_task_captures(
    root: Path,
) -> None:
    process = start_fac(root, "serve_captured")
    command_pid = int(wait_for(root / "build" / "pid"))

    process.send_signal(signal.SIGTERM)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:43:2: note: stopped task 'serve_captured'\nStopped after <elapsed>.\n"
    )
    assert (root / "build" / "terminated").exists()
    assert not is_running(command_pid)


@_POSIX_ONLY
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
    assert [is_running(pid) for pid in command_pids] == [False, False]
    assert not (root / "build" / "a.txt").exists()
    assert not (root / "build" / "b.txt").exists()


@_POSIX_ONLY
@pytest.mark.project("late_spawn")
def test_interrupt_ends_a_command_a_recipe_spawns_after_the_kill_before_it_runs(
    root: Path,
) -> None:
    process = start_fac(root, "-j2")
    wait_for(root / "build" / "hold.started")
    wait_for(root / "build" / "late.waiting")

    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 130, stderr
    assert (root / "build" / "hold.ended").exists()
    assert not (root / "build" / "late.ran").exists()


@_POSIX_ONLY
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


@_WINDOWS_ONLY
@pytest.mark.project("break_rule")
def test_ctrl_break_lets_the_rule_command_executing_finish_and_starts_no_other(
    root: Path,
) -> None:
    process = _start_fac_in_group(root)
    wait_for(root / "build" / "pid")

    _send_ctrl_break(process)
    (root / "go").touch()
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == "Stopped after <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "slow.txt").exists()
    assert not (root / "build" / "after.txt").exists()
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 1 output up to date."


@_WINDOWS_ONLY
@pytest.mark.project("break_task")
def test_ctrl_break_kills_the_task_command_that_ignores_it_after_the_grace(root: Path) -> None:
    process = _start_fac_in_group(root, "serve")
    command_pid = int(wait_for(root / "build" / "pid"))

    _send_ctrl_break(process)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:15:2: note: stopped task 'serve'\nStopped after <elapsed>.\n"
    )
    assert not is_running(command_pid)


@_WINDOWS_ONLY
@pytest.mark.project("stop")
def test_ctrl_break_stops_a_task_whose_command_ends_on_it(root: Path) -> None:
    process = _start_fac_in_group(root, "serve")
    command_pid = int(wait_for(root / "build" / "pid"))

    _send_ctrl_break(process)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:29:2: note: stopped task 'serve'\nStopped after <elapsed>.\n"
    )
    assert not is_running(command_pid)


@_WINDOWS_ONLY
@pytest.mark.project("live_break")
def test_ctrl_break_lets_a_rule_s_live_command_finish(
    root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outcome = run_in_new_console(_LIVE_DRIVER, tmp_path_factory.mktemp("live"), root, "break")

    assert outcome["status"] == 143
    assert (root / "build" / "slow.txt").read_text() == "slow"
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 1 output up to date."


@_WINDOWS_ONLY
@pytest.mark.project("live_ctrl_c")
def test_ctrl_c_kills_a_rule_s_live_command_on_windows(
    root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outcome = run_in_new_console(_LIVE_DRIVER, tmp_path_factory.mktemp("live"), root, "ctrl_c")
    command_pid = int((root / "build" / "pid").read_text())

    assert outcome["status"] == 130
    assert not is_running(command_pid)
    assert not (root / "build" / "slow.txt").exists()


@_WINDOWS_ONLY
@pytest.mark.project("two")
def test_ctrl_c_kills_every_running_command_on_windows(
    root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outcome = run_in_new_console(_CTRL_C_DRIVER, tmp_path_factory.mktemp("ctrl_c"), root)
    command_pids = [int((root / "build" / name).read_text()) for name in ("a.pid", "b.pid")]

    assert outcome["status"] == 130, outcome["stderr"]
    assert mask_elapsed(outcome["stderr"]) == (
        "fac.py:12:2: note: interrupted rule 'sleep' (build/a.txt), and 1 more recipe\n"
        "Interrupted after <elapsed>.\n"
    )
    assert [is_running(pid) for pid in command_pids] == [False, False]
    assert not (root / "build" / "a.txt").exists()
    assert not (root / "build" / "b.txt").exists()
