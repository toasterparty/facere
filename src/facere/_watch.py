"""Watch mode: a supervisor that runs no collection and holds no lock. Each cycle it starts a fresh `fac` on the same arguments, which records in the state what it observed, then polls that until a change in content or directory entries, and starts the next cycle, stopping one still running first.

A process per cycle, rather than an invocation in this one, since Python cannot kill a thread, so a recipe serving from Python itself could never be restarted.
"""

import os
import signal
import subprocess
import sys
import time

from facere import _state
from facere._cache import Entry, poll_directory, poll_file
from facere._diagnostics import format_path
from facere._filesystem import FileSystems
from facere._observed import ABSENT
from facere._schedule import Signals, watch_signals
from facere._summary import Outcome, Summary, format_summary

WATCHING = "fac: watching for changes"
"""The line that ends each cycle, for an editor to match."""
_POLL_S = 0.5
# How long no further change must arrive before a cycle starts, so Save All and a formatter's rewrite start one.
_QUIET_S = 0.1
# How long an interrupted cycle gets to end on its own, as one the terminal's Ctrl-C reached does, before it is
# interrupted itself.
_INTERRUPT_WAIT_S = 2.0
_SHOWN_PATHS = 3
_ROOT_FAC_PY = "fac.py"


def watch(cycle_args: list[str], root: str, state_path: str, targets: str) -> int:
    """Run a cycle of `fac CYCLE_ARGS...` whenever what the last one observed changes, until interrupted or stopped, and return the exit status, after printing the closing line. `state_path` is where each cycle records what it observed, under `targets`."""
    start_s = time.perf_counter()
    with watch_signals() as signals:
        outcome = _Supervisor(cycle_args, root, state_path, targets, signals).run()
    print(format_summary(Summary(), time.perf_counter() - start_s, outcome), file=sys.stderr)
    if signals.is_hung_up and sys.platform != "win32":
        # Everything is cleaned up, so the signal now ends the process as it would have.
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGHUP)
    return outcome.value


class _Supervisor:
    """The watch: what the last cycle observed, `files` and `dirs` each mapping a path to the digest the cycle found, and this process's latest look at each, which a stat vouches for as the hash cache's entries are vouched for."""

    def __init__(
        self, cycle_args: list[str], root: str, state_path: str, targets: str, signals: Signals
    ) -> None:
        self._cycle_args = cycle_args
        self._root = root
        self._start_dir = os.getcwd()
        self._state_path = state_path
        self._targets = targets
        self._signals = signals
        self._file_systems = FileSystems()
        self._files: dict[str, str] = {}
        self._dirs: dict[str, str] = {}
        self._outputs: frozenset[str] = frozenset()
        self._file_looks: dict[str, Entry | None] = {}
        self._dir_looks: dict[str, Entry | None] = {}
        # The digest of the observation loaded last, which changes whenever a cycle saves another.
        self._loaded_digest: str | None = None
        # Each path, keyed as _calc_looked keys it, whose change started a cycle that did not finish, with the digest
        # it had then.
        self._handed: dict[str, str] = {}
        self._cycle: subprocess.Popen[bytes] | None = None

    def run(self) -> Outcome:
        try:
            return self._watch()
        except KeyboardInterrupt:
            self._end_cycle()
            return Outcome.INTERRUPTED
        except OSError as error:
            print(f"fac: error: watch mode could not start a cycle: {error}", file=sys.stderr)
            return Outcome.UNSTARTED

    def _watch(self) -> Outcome:
        changed: list[str] = []
        while True:
            if changed:
                print(f"fac: change in {self._format_paths(changed)}", file=sys.stderr, flush=True)
            looked = self._calc_looked(is_cycling=False)
            handed = {path: looked[path] for path in changed}
            moved, status = self._run_cycle()
            if self._signals.is_stop_requested:
                return Outcome.STOPPED
            # A cycle that did not finish, as one that failed collection, may have left what started it unread, so
            # until a cycle finishes, those changes count no more.
            if status == Outcome.FINISHED.value:
                self._handed.clear()
            else:
                self._handed.update(handed)
            print(WATCHING, file=sys.stderr, flush=True)
            self._load()
            found = self._wait_for_change(moved)
            if found is None:
                return Outcome.STOPPED
            changed = found

    def _run_cycle(self) -> tuple[list[str], int]:
        """Run one cycle, asking it to stop gracefully once something it may already have read changes, and return what changed during it with the cycle's exit status.

        Each path is compared against what the cycle recorded of it, once it saves what it observed, as it does before a task, which may never end, and until then against what this process saw as the cycle started.
        """
        cycle = self._cycle = self._start_cycle()
        before = self._calc_looked(is_cycling=True)
        moved: list[str] = []
        is_stop_sent = False
        while True:
            try:
                status = cycle.wait(_POLL_S)
                break
            except subprocess.TimeoutExpired:
                pass
            if not moved:
                if (
                    _state.fetch_observation_digest(self._state_path, self._targets)
                    != self._loaded_digest
                ):
                    self._load()
                    before.update(self._calc_observed(is_cycling=True))
                self._sweep(is_cycling=True)
                looked = self._calc_looked(is_cycling=True)
                moved = sorted(
                    path for path, digest in looked.items() if before.get(path, digest) != digest
                )
            if (moved or self._signals.is_stop_requested) and not is_stop_sent:
                _stop(cycle)
                is_stop_sent = True
        self._cycle = None
        return moved, status

    def _start_cycle(self) -> subprocess.Popen[bytes]:
        command = [sys.executable, "-m", "facere", "--watched", *self._cycle_args]
        if sys.platform == "win32":
            # So CTRL_BREAK_EVENT reaches the cycle alone. The cycle turns Ctrl-C, which this disables, back on.
            return subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        return subprocess.Popen(command)

    def _end_cycle(self) -> None:
        """Wait for an interrupted cycle to end, interrupting it where the interrupt did not reach it, and killing it at a second interrupt."""
        cycle = self._cycle
        if cycle is None:
            return
        try:
            try:
                cycle.wait(_INTERRUPT_WAIT_S)
            except subprocess.TimeoutExpired:
                _interrupt(cycle)
                cycle.wait()
        except KeyboardInterrupt:
            cycle.kill()
            cycle.wait()

    def _load(self) -> None:
        """Take what the last cycle observed as what to compare against, starting each new path's look from the hash cache's entry."""
        loaded = _state.load_observation(self._state_path, self._targets)
        if loaded is None:
            self._loaded_digest = None
            observation = _state.Observation({}, {}, frozenset())
            entries = {}
        else:
            self._loaded_digest, observation = loaded
            entries = _state.load(self._state_path).hashes
        files = dict(observation.files)
        # A cycle that failed before collection observed nothing, so writing the root's fac.py starts the next.
        if _ROOT_FAC_PY not in files:
            files[_ROOT_FAC_PY] = self._digest(self._look_file(_ROOT_FAC_PY, None, time.time_ns()))
        self._files = files
        self._dirs = dict(observation.dirs)
        self._outputs = observation.outputs
        self._file_looks = {
            path: self._file_looks.get(path) or entries.get(path) for path in self._files
        }
        self._dir_looks = {path: self._dir_looks.get(path) for path in self._dirs}

    def _wait_for_change(self, moved: list[str]) -> list[str] | None:
        """Wait until what differs from what the last cycle observed has stopped changing, and return it with `moved`, what changed during that cycle, or None once a stop is asked for. A cycle a change stopped is followed at once."""
        while True:
            if not moved:
                self._sweep(is_cycling=False)
                while not self._find_changed():
                    if self._sleep(_POLL_S):
                        return None
                    self._sweep(is_cycling=False)
            while True:
                looked = self._calc_looked(is_cycling=False)
                if self._sleep(_QUIET_S):
                    return None
                self._sweep(is_cycling=False)
                if self._calc_looked(is_cycling=False) == looked:
                    break
            changed = sorted({*self._find_changed(), *moved})
            if changed:
                return changed

    def _sleep(self, seconds: float) -> bool:
        """Sleep for `seconds`, and return whether a stop was asked for."""
        time.sleep(seconds)
        return self._signals.is_stop_requested

    def _sweep(self, *, is_cycling: bool) -> None:
        """Look at each path again, which while `is_cycling` leaves out the outputs, which the cycle writes."""
        start_ns = time.time_ns()
        for path in self._files:
            if not (is_cycling and path in self._outputs):
                self._file_looks[path] = self._look_file(path, self._file_looks[path], start_ns)
        for path in self._dirs:
            if not (is_cycling and path in self._outputs):
                absolute = os.path.join(self._root, path)
                last = self._dir_looks[path]
                self._dir_looks[path] = poll_directory(absolute, last, start_ns, self._file_systems)

    def _look_file(self, path: str, last: Entry | None, start_ns: int) -> Entry | None:
        absolute = os.path.join(self._root, path)
        return poll_file(absolute, last, start_ns, self._file_systems)

    def _calc_looked(self, *, is_cycling: bool) -> dict[str, str]:
        """Return the digest of each path as last looked at, which while `is_cycling` leaves out the outputs. A directory's path ends in `/`."""
        looked = {
            path: self._digest(look)
            for path, look in self._file_looks.items()
            if not (is_cycling and path in self._outputs)
        }
        looked.update(
            (f"{path}/", self._digest(look))
            for path, look in self._dir_looks.items()
            if not (is_cycling and path in self._outputs)
        )
        return looked

    def _calc_observed(self, *, is_cycling: bool) -> dict[str, str]:
        """Return the digest the last cycle observed of each path, keyed as _calc_looked keys them."""
        observed = {
            path: digest
            for path, digest in self._files.items()
            if not (is_cycling and path in self._outputs)
        }
        observed.update(
            (f"{path}/", digest)
            for path, digest in self._dirs.items()
            if not (is_cycling and path in self._outputs)
        )
        return observed

    def _find_changed(self) -> list[str]:
        """Return each path whose content or entries, as last looked at, differ from what the last cycle observed and from what started a cycle that did not finish, keyed as _calc_looked keys them."""
        looked = self._calc_looked(is_cycling=False)
        return [
            path
            for path, digest in self._calc_observed(is_cycling=False).items()
            if looked[path] not in (digest, self._handed.get(path))
        ]

    @staticmethod
    def _digest(look: Entry | None) -> str:
        return ABSENT if look is None else look.digest

    def _format_paths(self, paths: list[str]) -> str:
        """Return `paths`, each relative to the root and a directory's ending in `/`, as the line starting a cycle names them, relative to the working directory."""
        shown = [
            format_path(os.path.join(self._root, path.rstrip("/")), self._start_dir)
            + ("/" if path.endswith("/") else "")
            for path in paths[:_SHOWN_PATHS]
        ]
        others = len(paths) - len(shown)
        if others:
            shown.append(f"and {others} more")
        return ", ".join(shown)


def _stop(cycle: subprocess.Popen[bytes]) -> None:
    """Ask `cycle` for a graceful stop."""
    if sys.platform == "win32":
        cycle.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        cycle.send_signal(signal.SIGTERM)


def _interrupt(cycle: subprocess.Popen[bytes]) -> None:
    """Interrupt `cycle`, or on Windows, where no Ctrl-C can be sent to one process, stop it."""
    if sys.platform == "win32":
        cycle.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        cycle.send_signal(signal.SIGINT)
