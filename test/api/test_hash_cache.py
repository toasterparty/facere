"""The hash cache trusts a file's stat to vouch for its content, except where the file changed too recently for the stat to show a later change, or lies on a file system whose timestamps prove nothing."""

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ..helpers import Fac

EXECUTED_ONE = "Finished in <elapsed>. Executed 1 rule.\n"
UP_TO_DATE_ONE = "Finished in <elapsed>. No work to do. 1 output up to date.\n"
SETTLE_NS = 10_000_000_000

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="needs cp and /proc")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="needs symlinks")


@pytest.fixture
def later_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every invocation 10 s after now, so every file the test wrote has settled."""
    clock = SimpleNamespace(time_ns=lambda: time.time_ns() + SETTLE_NS)
    monkeypatch.setattr("facere._cache.time", clock)


@pytest.fixture
def blind_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make a stat show only a file's size, as a stat on a coarse file system shows an edit that keeps it."""

    def calc_stamp(_: str, info: os.stat_result) -> tuple[str, int]:
        return f"{info.st_size}", max(info.st_mtime_ns, info.st_ctime_ns)

    monkeypatch.setattr("facere._cache._calc_stamp", calc_stamp)


def wait_for_later_change_time(path: Path) -> None:
    """Return once a file written now gets a later change time than `path`, as an edit made after an invocation does once the file system's clock ticks."""
    probe = path.with_name(".tick")
    probe.write_bytes(b"")
    while probe.stat().st_ctime_ns <= path.stat().st_ctime_ns:
        probe.write_bytes(b"")
    probe.unlink()


@pytest.mark.usefixtures("blind_stats")
@pytest.mark.project("copy")
def test_edit_the_stat_misses_soon_after_the_last_change_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "a.txt").write_text("ho")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "a.txt").read_text() == "ho"


@pytest.mark.usefixtures("blind_stats", "later_clock")
@pytest.mark.project("copy")
def test_settled_file_costs_a_stat_and_no_read(root: Path, fac: Fac) -> None:
    fac()
    (root / "a.txt").write_text("ho")

    assert fac().err == UP_TO_DATE_ONE


@linux_only
@pytest.mark.usefixtures("blind_stats", "later_clock")
@pytest.mark.project("copy")
def test_file_on_a_network_file_system_is_read_on_every_invocation(
    root: Path, fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert sys.platform == "linux"
    device = os.stat(root).st_dev
    mount = f"36 25 {os.major(device)}:{os.minor(device)} / / rw - nfs4 server:/export rw\n"
    monkeypatch.setattr("facere._filesystem._read_mountinfo", lambda: mount)
    fac()
    (root / "a.txt").write_text("ho")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "a.txt").read_text() == "ho"


@linux_only
@pytest.mark.usefixtures("later_clock")
@pytest.mark.project("copy")
def test_same_size_replacement_keeping_the_old_mtime_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    older = root / "older.txt"
    older.write_text("ho")
    os.utime(older, ns=(0, os.stat(root / "a.txt").st_mtime_ns))
    wait_for_later_change_time(root / "a.txt")

    subprocess.run(["cp", "-p", older, root / "a.txt"], check=True)

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "a.txt").read_text() == "ho"


@pytest.mark.usefixtures("later_clock")
@pytest.mark.project("copy")
def test_output_edited_by_hand_after_it_settled_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    wait_for_later_change_time(root / "build" / "a.txt")
    (root / "build" / "a.txt").write_text("ho")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "a.txt").read_text() == "hi"


@posix_only
@pytest.mark.project("linked_tree")
def test_links_in_an_input_tree_that_loop_or_dangle_hash_as_their_text(
    root: Path, fac: Fac
) -> None:
    os.symlink(".", root / "tree" / "loop")
    os.symlink("missing", root / "tree" / "dangling")
    assert fac().err == EXECUTED_ONE
    assert fac().err == UP_TO_DATE_ONE

    os.remove(root / "tree" / "dangling")
    os.symlink("elsewhere", root / "tree" / "dangling")

    assert fac().err == EXECUTED_ONE


@pytest.mark.project("regenerated")
def test_file_back_in_a_directory_output_after_a_regeneration_dropped_it_makes_the_rule_stale(
    root: Path, fac: Fac
) -> None:
    fac("generate")
    (root / "names.txt").write_text("version.h\n")
    fac()
    (root / "names.txt").write_text("version.h\nconfig.h\n")

    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "main.o").read_text() == "generated"
