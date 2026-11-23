"""The command line, run as `python -m facere` in a subprocess."""

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from facere._version import VERSION

from ..helpers import mask_elapsed, run_fac


def test_version_prints_the_version(tmp_path: Path) -> None:
    result = run_fac(tmp_path, "--version")

    assert result.status == 0, result.err
    assert result.out == f"{VERSION}\n"


def test_help_documents_every_flag_and_exit_status_without_a_fac_py(tmp_path: Path) -> None:
    result = run_fac(tmp_path, "--help")

    assert result.status == 0, result.err
    documented = (
        "TARGET",
        "-C DIR",
        "--out DIR",
        "--jobs N",
        "--keep-going",
        "--lock-timeout SECONDS",
        "--quiet",
        "--verbose",
        "--version",
        "--",
    )
    for flag in documented:
        assert flag in result.out
    for status in ("0", "1", "2", "3", "4", "130", "143"):
        assert f"\n  {status} " in result.out


@pytest.mark.project("verbose")
def test_verbose_prints_each_command_as_one_quoted_string(root: Path) -> None:
    result = run_fac(root, "--verbose", "say")

    assert result.status == 0, result.err
    python = shlex.quote(sys.executable)
    assert result.err.splitlines() == [
        f"{python} -c pass 'two words'",
        "Finished in <elapsed>. Executed 1 task.",
    ]


@pytest.mark.project("verbose")
def test_commands_stay_unprinted_without_verbose(root: Path) -> None:
    assert run_fac(root, "say").err == "Finished in <elapsed>. Executed 1 task.\n"


@pytest.mark.project("touch")
def test_successful_build_exits_zero(root: Path) -> None:
    result = run_fac(root)

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("exit")
def test_failed_build_exits_one(root: Path) -> None:
    result = run_fac(root)

    assert result.status == 1
    assert result.err.splitlines()[-2] == "fac.py:4:2: error: rule 'touch' (build/a.txt) failed"


@pytest.mark.project("touch")
def test_unknown_flag_exits_two(root: Path) -> None:
    result = run_fac(root, "--no-such-flag")

    assert result.status == 2
    assert result.err.splitlines()[-1] == "fac: error: unrecognized arguments: --no-such-flag"


@pytest.mark.project("touch")
def test_disabled_assertions_print_a_one_line_warning(root: Path) -> None:
    result = run_fac(root, python_flags=("-O",))

    assert result.status == 0
    assert result.err.splitlines() == [
        "fac: warning: Python runs with assertions disabled, so no recipe's assert checks anything",
        "Finished in <elapsed>. Executed 1 rule.",
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
    assert (
        mask_elapsed(stderr)
        == "fac.py:8:2: note: interrupted rule 'slow' (build/a.txt)\nInterrupted after <elapsed>.\n"
    )
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    (root / "a.txt").write_text("a")
    (root / "block").unlink()
    assert run_fac(root).err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("touch")
def test_directory_flag_frames_the_output_with_the_directory_entered(root: Path) -> None:
    result = run_fac(root.parent, "-C", root.name)

    assert result.status == 0, result.err
    assert result.err.splitlines() == [
        f"fac: Entering directory '{root}'",
        f"fac: Leaving directory '{root}'",
        "Finished in <elapsed>. Executed 1 rule.",
    ]


def test_bug_in_facere_exits_four_with_its_traceback(root: Path) -> None:
    (root / "fac.py").write_text("")
    # Stands in for a bug: collection itself raises.
    breaking = "import sys, facere, facere._collect; facere._collect.collect = None; sys.exit(facere.main([]))"

    completed = subprocess.run(
        [sys.executable, "-c", breaking], cwd=root, capture_output=True, text=True, check=False
    )

    assert completed.returncode == 4, completed.stderr
    lines = mask_elapsed(completed.stderr).splitlines()
    assert lines[0] == "Traceback (most recent call last):"
    assert lines[-3:] == [
        "TypeError: 'NoneType' object is not callable",
        "fac: error: Facere itself raised this, which is a bug in Facere",
        "Failed after <elapsed>.",
    ]
