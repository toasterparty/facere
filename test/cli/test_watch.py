"""`fac --watch` builds its targets, then builds them again on each change to what the last build read, restarting the tasks among them."""

import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from ..helpers import edit, mask_elapsed, wait_for

WATCHING = "fac: watching for changes"
_DEADLINE_S = 30


class _Watch:
    """`fac --watch ARGS...` running in `root`, whose stderr lines a thread collects."""

    def __init__(self, root: Path, *args: str) -> None:
        command = [sys.executable, "-m", "facere", "--watch", *args]
        if sys.platform == "win32":
            # So CTRL_BREAK_EVENT reaches the watch alone, and never the test runner.
            self.process = subprocess.Popen(
                command,
                cwd=root,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            self.process = subprocess.Popen(command, cwd=root, stderr=subprocess.PIPE, text=True)
        self._lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def read_line(self) -> str:
        """Return the next line, with its elapsed time masked, waiting for it as long as the deadline allows."""
        try:
            return mask_elapsed(self._lines.get(timeout=_DEADLINE_S))
        except queue.Empty:
            raise AssertionError("fac --watch printed no line before the deadline") from None

    def read_cycle(self) -> list[str]:
        """Return the lines up to the next that ends a cycle, which it includes."""
        lines = [self.read_line()]
        while lines[-1] != WATCHING:
            lines.append(self.read_line())
        return lines

    def stop(self) -> int:
        """Stop the watch gracefully, and return its exit status."""
        if self.process.poll() is None:
            self.process.send_signal(
                signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM
            )
        try:
            return self.process.wait(_DEADLINE_S)
        except subprocess.TimeoutExpired:
            self.process.kill()
            raise

    def _read(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self._lines.put(line.rstrip("\n"))


@pytest.fixture
def watch(root: Path) -> Iterator[Callable[..., _Watch]]:
    """Return a function starting `fac --watch ARGS...` in the root, each stopped as the test ends."""
    started: list[_Watch] = []

    def start(*args: str) -> _Watch:
        started.append(_Watch(root, *args))
        return started[-1]

    yield start
    for session in started:
        session.stop()


def _wait_for_text(path: Path, text: str) -> None:
    deadline = time.monotonic() + _DEADLINE_S
    while not (path.exists() and path.read_text() == text):
        assert time.monotonic() < deadline, f"{path} never held {text!r}"
        time.sleep(0.01)


@pytest.mark.project("copy")
def test_a_save_rebuilds(root: Path, watch: Callable[..., _Watch]) -> None:
    session = watch("copy")
    assert session.read_cycle() == ["Finished in <elapsed>. Executed 1 rule.", WATCHING]

    (root / "source.txt").write_text("two\n")

    assert session.read_cycle() == [
        "fac: change in source.txt",
        "Finished in <elapsed>. Executed 1 rule.",
        WATCHING,
    ]
    assert (root / "build" / "copy.txt").read_text() == "two\nother\n"


@pytest.mark.project("copy")
def test_an_unchanged_save_a_touch_and_facere_s_own_writes_start_no_cycle(
    root: Path, watch: Callable[..., _Watch]
) -> None:
    session = watch("copy")
    session.read_cycle()

    (root / "source.txt").write_text("one\n")
    (root / "source.txt").touch()
    (root / "other.txt").write_text("changed\n")

    # Had the first cycle's own output or either write to source.txt counted, the line would name it.
    assert session.read_cycle()[0] == "fac: change in other.txt"


@pytest.mark.project("copy")
def test_a_hand_edited_output_rebuilds(root: Path, watch: Callable[..., _Watch]) -> None:
    session = watch("copy")
    session.read_cycle()

    (root / "build" / "copy.txt").write_text("edited\n")

    assert session.read_cycle() == [
        "fac: change in build/copy.txt",
        "Finished in <elapsed>. Executed 1 rule.",
        WATCHING,
    ]
    assert (root / "build" / "copy.txt").read_text() == "one\nother\n"


@pytest.mark.project("stop")
def test_a_change_during_a_cycle_stops_it_gracefully_and_the_next_cycle_finishes(
    root: Path, watch: Callable[..., _Watch]
) -> None:
    session = watch("slow")
    session.read_cycle()
    (root / "source.txt").write_text("wait\n")
    wait_for(root / "build" / "started")

    (root / "source.txt").write_text("two\n")

    assert session.read_cycle() == [
        "fac: change in source.txt",
        "Stopped after <elapsed>. Executed 1 rule.",
        WATCHING,
    ]
    assert session.read_cycle() == [
        "fac: change in source.txt",
        "Finished in <elapsed>. Executed 1 rule.",
        WATCHING,
    ]
    assert (root / "build" / "slow.txt").read_text() == "two\n"


@pytest.mark.project("serve")
def test_a_change_restarts_a_named_task(root: Path, watch: Callable[..., _Watch]) -> None:
    session = watch("serve")
    starts = root / "build" / "starts.txt"
    _wait_for_text(starts, "one\n")

    (root / "source.txt").write_text("two\n")

    assert session.read_cycle()[-2:] == ["Stopped after <elapsed>.", WATCHING]
    assert session.read_line() == "fac: change in source.txt"
    _wait_for_text(starts, "one\ntwo\n")
    assert session.stop() == 143


@pytest.mark.project("copy")
def test_a_failed_collection_keeps_watching_and_recovers_once_fac_py_is_fixed(
    root: Path, watch: Callable[..., _Watch]
) -> None:
    session = watch("copy")
    session.read_cycle()
    edit(root / "fac.py", "def copy(", "def copy(:")
    assert session.read_cycle()[::3] == ["fac: change in fac.py", WATCHING]

    # What the last collected cycle read still starts a cycle.
    (root / "source.txt").write_text("two\n")
    assert session.read_cycle()[0] == "fac: change in source.txt"

    edit(root / "fac.py", "def copy(:", "def copy(")
    assert session.read_cycle() == [
        "fac: change in fac.py",
        "Finished in <elapsed>. Executed 1 rule.",
        WATCHING,
    ]
    assert (root / "build" / "copy.txt").read_text() == "two\nother\n"
