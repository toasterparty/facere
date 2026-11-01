"""The command line, run as `python -m facere` in a subprocess."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.helpers import run_fac


def test_version_prints_the_version(tmp_path: Path) -> None:
    result = run_fac(tmp_path, "--version")

    assert result.status == 0, result.err
    assert result.out == "0.1.0\n"


@pytest.mark.project("touch")
def test_successful_build_exits_zero(root: Path) -> None:
    result = run_fac(root)

    assert result.status == 0, result.err
    assert result.err == "fac: 1 executed, 0 up to date\n"


@pytest.mark.project("exit")
def test_failed_build_exits_one(root: Path) -> None:
    result = run_fac(root)

    assert result.status == 1
    assert result.err.splitlines()[-1] == "fac.py:4:2: error: rule 'touch' (build/a.txt) failed"


@pytest.mark.project("touch")
def test_unknown_flag_exits_two(root: Path) -> None:
    result = run_fac(root, "--jobs")

    assert result.status == 2
    assert result.err.splitlines()[-1] == "fac: error: unrecognized arguments: --jobs"


@pytest.mark.project("touch")
def test_disabled_assertions_print_a_one_line_warning(root: Path) -> None:
    result = run_fac(root, python_flags=("-O",))

    assert result.status == 0
    assert result.err.splitlines() == [
        "fac: warning: Python runs with assertions disabled, so no recipe's assert checks anything: drop -O and PYTHONOPTIMIZE",
        "fac: 1 executed, 0 up to date",
    ]


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGINT reaches a process this way only on POSIX"
)
@pytest.mark.project("interrupt")
def test_interrupt_kills_the_running_command_and_leaves_its_rule_unrecorded(root: Path) -> None:
    assert run_fac(root).status == 0
    (root / "a.txt").write_text("b")
    (root / "block").touch()
    pid_file = root / "build" / "pid"
    pid_file.unlink()

    process = subprocess.Popen(
        [sys.executable, "-m", "facere"], cwd=root, stderr=subprocess.PIPE, text=True
    )
    deadline = time.monotonic() + 30
    while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
        time.sleep(0.05)
    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 130, stderr
    assert stderr == "fac: interrupted\n"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    (root / "a.txt").write_text("a")
    (root / "block").unlink()
    assert run_fac(root).err == "fac: 1 executed, 0 up to date\n"
