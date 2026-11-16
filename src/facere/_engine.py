"""The dependency engine: which steps are stale, why, and in what order they run.

A key is anything with a digest, such as a file, and a step is work the host runs that reads keys and writes keys. A step is stale by comparing digests against its trace, the record of its last success, so a step that runs again to the same digests leaves the steps after it current.

The engine does no I/O and no hashing, starts no thread, takes no lock, and imports nothing from Facere. The host polls it for events and answers each one:

    engine.request(targets)
    while (event := engine.poll()) is not Pause.DONE:
        NeedDigests: observe each key, then give_digests
        Run: forget the step's saved trace, run the step, then finish
        Built: save the trace, or note the step stays stale where it holds none
        Failed: report it
        Pause.IDLE: wait for another worker's answer

Every call returns at once and none calls the host, so a host with several workers holds one mutex of its own across each call, runs the same loop on each worker, and wakes the idle ones after every answer. The engine hands each event out once, to the caller that polled it, a Run only once every step upstream of its step is settled, and among the steps that are ready, the one declared first.
"""

import enum
import heapq
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import NamedTuple

__all__ = [
    "Built",
    "Engine",
    "Event",
    "Failed",
    "Graph",
    "Key",
    "Missing",
    "NeedDigests",
    "Pause",
    "Reason",
    "Run",
    "Status",
    "Step",
    "Trace",
    "Verdict",
    "decide",
]

Key = str

_UNKNOWN = object()


class Step(NamedTuple):
    """Work that reads `inputs` and writes `outputs`, ordered after the steps that write its `inputs` and `order_only` keys.

    `digest` covers everything that decides what the step writes but the content of its inputs, the keys it declares included. A step in a `pool` runs only while the pool has room.
    """

    digest: str
    inputs: tuple[Key, ...] = ()
    order_only: tuple[Key, ...] = ()
    outputs: tuple[Key, ...] = ()
    is_always: bool = False
    pool: str | None = None


class Trace(NamedTuple):
    """A step's last success: its digest, and each key it read and wrote with that key's digest. `found` holds the inputs it reported as it finished."""

    digest: str
    inputs: tuple[tuple[Key, str], ...]
    outputs: tuple[tuple[Key, str], ...]
    found: tuple[tuple[Key, str], ...]


class Reason(enum.Enum):
    """What a step's check found. Only CURRENT leaves it as it is, and INPUT_MISSING fails it without running it."""

    CURRENT = enum.auto()
    INPUT_MISSING = enum.auto()
    ALWAYS = enum.auto()
    NO_TRACE = enum.auto()
    STEP_CHANGED = enum.auto()
    INPUT_CHANGED = enum.auto()
    OUTPUT_CHANGED = enum.auto()


class Verdict(NamedTuple):
    """Why a step runs or doesn't, with the key that decided it where one did."""

    reason: Reason
    key: Key | None = None


class Status(enum.Enum):
    """How a step's run ended. UNSETTLED succeeded, but must run again next time, so it leaves no trace."""

    OK = enum.auto()
    FAILED = enum.auto()
    UNSETTLED = enum.auto()


class Missing(enum.Enum):
    """What a step lacks that fails it: an input before it runs, or an output or a found input once it succeeded."""

    INPUT = enum.auto()
    OUTPUT = enum.auto()
    FOUND = enum.auto()


class NeedDigests(NamedTuple):
    """The engine needs the digest of each of `keys` as it is now, to check `step` or to settle it. Answer with give_digests."""

    step: int
    keys: tuple[Key, ...]


class Run(NamedTuple):
    """`step` is stale for the reason in `verdict`. Run it, then answer with finish."""

    step: int
    verdict: Verdict


class Built(NamedTuple):
    """`step` ran and wrote every output. `trace` is its new trace to save, or None where it finished UNSETTLED."""

    step: int
    trace: Trace | None


class Failed(NamedTuple):
    """The engine failed `step` because `key` has no digest."""

    step: int
    missing: Missing
    key: Key


class Pause(enum.Enum):
    """Nothing to hand out: for now, while other workers hold the events everything left waits on, or for good."""

    IDLE = enum.auto()
    DONE = enum.auto()


Event = NeedDigests | Run | Built | Failed | Pause


class _State(enum.Enum):
    UNWANTED = enum.auto()
    WAITING = enum.auto()
    READY = enum.auto()
    CHECKING = enum.auto()
    STALE = enum.auto()
    RUNNING = enum.auto()
    FINISHING = enum.auto()
    CURRENT = enum.auto()
    BUILT = enum.auto()
    FAILED = enum.auto()
    SKIPPED = enum.auto()


_DONE_STATES = (_State.CURRENT, _State.BUILT)
_FAILED_STATES = (_State.FAILED, _State.SKIPPED)


class Graph:
    """Steps and the keys that order them. A step is known by its index in `steps`.

    `producers` maps each key a step outputs to that step, and `duplicates` each key several steps output to all of them. `upstream` holds, per step, the steps that output a key it reads or is ordered after. `cycle` is None, or the steps of one dependency cycle, each with the key it reads that the next one outputs, the last wrapping to the first.
    """

    def __init__(self, steps: Sequence[Step]) -> None:
        self.steps = tuple(steps)
        producers: dict[Key, int] = {}
        duplicates: dict[Key, list[int]] = {}
        for index, step in enumerate(self.steps):
            for key in step.outputs:
                first = producers.setdefault(key, index)
                if first != index:
                    duplicates.setdefault(key, [first]).append(index)
        self.producers: Mapping[Key, int] = producers
        self.duplicates: Mapping[Key, Sequence[int]] = duplicates
        self.upstream = tuple(
            tuple(
                dict.fromkeys(
                    producers[key] for key in (*step.inputs, *step.order_only) if key in producers
                )
            )
            for step in self.steps
        )
        self.cycle = self._find_cycle()

    def _find_cycle(self) -> tuple[tuple[int, Key], ...] | None:
        producers = self.producers
        done: set[int] = set()
        for start in range(len(self.steps)):
            if start in done:
                continue
            path = [start]
            keys: list[Key] = []
            edges = [self._iter_edges(start)]
            while path:
                key = next(edges[-1], None)
                if key is None:
                    done.add(path.pop())
                    edges.pop()
                    if keys:
                        keys.pop()
                    continue
                producer = producers[key]
                if producer in done:
                    continue
                if producer in path:
                    first = path.index(producer)
                    return tuple(zip(path[first:], [*keys, key][first:], strict=True))
                path.append(producer)
                keys.append(key)
                edges.append(self._iter_edges(producer))
        return None

    def _iter_edges(self, index: int) -> Iterator[Key]:
        step = self.steps[index]
        return (key for key in (*step.inputs, *step.order_only) if key in self.producers)


def _decide_by_inputs(
    step: Step, trace: Trace | None, digests: Mapping[Key, str | None]
) -> Verdict | None:
    """Return why `step` runs or fails given its inputs, whose digests are all known, or None where its trace matches them."""
    inputs = step.inputs
    for key in inputs:
        if digests[key] is None:
            return Verdict(Reason.INPUT_MISSING, key)
    if step.is_always:
        return Verdict(Reason.ALWAYS)
    if trace is None:
        return Verdict(Reason.NO_TRACE)
    if trace.digest != step.digest:
        return Verdict(Reason.STEP_CHANGED)
    if trace.inputs != tuple((key, digests[key]) for key in inputs):
        recorded = dict(trace.inputs)
        for key in inputs:
            if recorded.get(key) != digests[key]:
                return Verdict(Reason.INPUT_CHANGED, key)
    return None


def _decide_from(
    pending: tuple[tuple[Key, str], ...] | None,
    step: Step,
    trace: Trace | None,
    digests: Mapping[Key, str | None],
) -> tuple[Verdict | list[Key], tuple[tuple[Key, str], ...] | None]:
    """Decide as `decide` does, and return with the result where to resume once the keys it names have digests.

    `pending` is None to decide from the start. Otherwise the inputs matched the trace in an earlier call, and it holds the found inputs that call left without a digest, the only ones still to compare.
    """
    if pending is None:
        unknown = [key for key in step.inputs if key not in digests]
        if unknown:
            return unknown, None
        verdict = _decide_by_inputs(step, trace, digests)
        if verdict is not None:
            return verdict, None
    if trace is None:
        return Verdict(Reason.NO_TRACE), None
    unsettled = []
    for pair in trace.found if pending is None else pending:
        key, digest = pair
        current = digests.get(key, _UNKNOWN)
        if current == digest:
            continue
        if current is not _UNKNOWN:
            return Verdict(Reason.INPUT_CHANGED, key), None
        unsettled.append(pair)
    unknown = [key for key, _ in unsettled]
    unknown.extend(key for key in step.outputs if key not in digests)
    if unknown:
        return unknown, tuple(unsettled)
    recorded = dict(trace.outputs)
    for key in step.outputs:
        if digests[key] != recorded.get(key):
            return Verdict(Reason.OUTPUT_CHANGED, key), None
    return Verdict(Reason.CURRENT), None


def decide(
    step: Step, trace: Trace | None, digests: Mapping[Key, str | None]
) -> Verdict | list[Key]:
    """Return why `step` runs or doesn't, given its `trace` and the `digests` known, where None is the digest of a key with nothing there.

    Where the decision reads keys `digests` lacks, return those instead: first the inputs, then, once the trace matches them, the keys the trace found and the outputs, so a step known stale by its inputs has nothing further read.
    """
    return _decide_from(None, step, trace, digests)[0]


class Engine:
    """One session over a `graph`, which must hold no duplicate output and no cycle: digests are observed once and kept, and each step is checked and run at most once.

    With `keep_going`, a failure skips only the steps downstream of it, and otherwise it stops every step not yet running. `pool_sizes` gives how many steps of each pool may run at once. `total` counts the steps requested so far, with all upstream of them, and `verdicts` holds each one checked so far, in the order decided.
    """

    def __init__(
        self,
        graph: Graph,
        *,
        keep_going: bool = False,
        pool_sizes: Mapping[str, int] | None = None,
    ) -> None:
        assert not graph.duplicates and graph.cycle is None
        self._graph = graph
        self._steps = graph.steps
        self._keep_going = keep_going
        self._pool_free = dict(pool_sizes or {})
        assert all(step.pool is None or step.pool in self._pool_free for step in self._steps)
        assert all(size > 0 for size in self._pool_free.values())
        self._upstream = list(graph.upstream)
        self._traces: dict[int, Trace] = {}
        self._digests: dict[Key, str | None] = {}
        self._states = [_State.UNWANTED] * len(self._steps)
        self._blockers = [0] * len(self._steps)
        self._dependents: dict[int, list[int]] = {}
        self._doomed: set[int] = set()
        self._ready: list[int] = []
        self._stale: list[int] = []
        self._events: deque[Event] = deque()
        self._waiters: dict[Key, list[int]] = {}
        self._pending: dict[int, int] = {}
        # By step whose inputs matched its trace, the found inputs its check still waits on.
        self._unsettled: dict[int, tuple[tuple[Key, str], ...]] = {}
        self._inputs: dict[int, tuple[tuple[Key, str], ...]] = {}
        self._finishing: dict[int, tuple[Status, tuple[Key, ...]]] = {}
        self._running = 0
        self._has_stopped = False
        self.total = 0
        self.verdicts: dict[int, Verdict] = {}

    def load_trace(self, step: int, trace: Trace, follows: Iterable[Key] | None = None) -> bool:
        """Give the engine the saved `trace` of `step`, before the first request, and return whether it kept it.

        The step is ordered after the steps that now output one of `follows`, as it is after those of its declared inputs. `follows` defaults to the keys the trace found, and a host gives its own where reading a found key also reads another key, as a file read from inside a directory that a step outputs. A trace that would order its step after a step downstream of it is refused, since only running the step again shows what it reads now.
        """
        assert not self.total
        producers = self._graph.producers
        if follows is None:
            follows = [key for key, _ in trace.found]
        ordering = [key for key in follows if key in producers]
        if ordering:
            static = self._graph.upstream[step]
            added = sorted({producers[key] for key in ordering} - {step, *static})
            if any(self._reaches(producer, step) for producer in added):
                return False
            if added:
                self._upstream[step] = (*static, *added)
        self._traces[step] = trace
        return True

    def forget_trace(self, step: int) -> None:
        """Drop the trace of `step`, so it runs unless it was already checked."""
        self._traces.pop(step, None)

    def find_closure(self, targets: Iterable[int]) -> set[int]:
        """Return `targets` with every step upstream of them, which a request for them reaches."""
        closure: set[int] = set()
        stack = list(targets)
        while stack:
            step = stack.pop()
            if step not in closure:
                closure.add(step)
                stack.extend(self._upstream[step])
        return closure

    def request(self, targets: Iterable[int]) -> None:
        """Ask for `targets` to be made current, with every step upstream of them. A step an earlier request settled stays as it is."""
        states = self._states
        stack = list(targets)
        while stack:
            step = stack.pop()
            if states[step] is not _State.UNWANTED:
                continue
            states[step] = _State.WAITING
            self.total += 1
            blockers = 0
            for upstream in self._upstream[step]:
                state = states[upstream]
                if state in _DONE_STATES:
                    continue
                if state in _FAILED_STATES:
                    self._doomed.add(step)
                    continue
                blockers += 1
                self._dependents.setdefault(upstream, []).append(step)
                stack.append(upstream)
            self._blockers[step] = blockers
            if not blockers:
                self._unblock(step)

    def poll(self) -> Event:
        """Return the next event, which belongs to the caller alone, or a Pause."""
        while True:
            if self._events:
                return self._events.popleft()
            if not self._has_stopped:
                run = self._take_stale()
                if run is not None:
                    return run
                if self._ready:
                    self._check(heapq.heappop(self._ready))
                    continue
            return Pause.IDLE if self._waiters or self._running else Pause.DONE

    def give_digests(self, digests: Mapping[Key, str | None]) -> None:
        """Answer a NeedDigests with the digest of each of its keys, or None where nothing is there to read."""
        pending = self._pending
        for key, digest in digests.items():
            self._digests[key] = digest
            for step in self._waiters.pop(key):
                pending[step] -= 1
                if pending[step]:
                    continue
                del pending[step]
                if self._states[step] is _State.CHECKING:
                    self._check(step)
                else:
                    self._complete(step)

    def finish(self, step: int, status: Status, found: Iterable[Key] = ()) -> None:
        """Answer a Run for `step` with how it ended and, unless it failed, the inputs it `found` beyond those declared.

        Each found key must be settled already: no step outputs it, or one upstream of `step` does.
        """
        assert self._states[step] is _State.RUNNING
        self._running -= 1
        pool = self._steps[step].pool
        if pool is not None:
            self._pool_free[pool] += 1
        if status is Status.FAILED:
            self._fail(step)
            return
        found = tuple(found)
        self._states[step] = _State.FINISHING
        self._finishing[step] = (status, found)
        outputs = self._steps[step].outputs
        for key in outputs:
            self._digests.pop(key, None)
        if not self._ask(step, (*outputs, *found)):
            self._complete(step)

    def stop(self) -> None:
        """Hand out no further Run and check no further step. What is running finishes, then poll returns DONE."""
        self._has_stopped = True

    def _reaches(self, start: int, goal: int) -> bool:
        seen = {start}
        stack = [start]
        while stack:
            step = stack.pop()
            if step == goal:
                return True
            for upstream in self._upstream[step]:
                if upstream not in seen:
                    seen.add(upstream)
                    stack.append(upstream)
        return False

    def _take_stale(self) -> Run | None:
        """Return a Run for the stale step declared first whose pool has room, taking that room."""
        held = []
        run = None
        while self._stale and run is None:
            step = heapq.heappop(self._stale)
            pool = self._steps[step].pool
            if pool is not None and not self._pool_free[pool]:
                held.append(step)
                continue
            if pool is not None:
                self._pool_free[pool] -= 1
            self._states[step] = _State.RUNNING
            self._running += 1
            run = Run(step, self.verdicts[step])
        for step in held:
            heapq.heappush(self._stale, step)
        return run

    def _ask(self, step: int, keys: Iterable[Key]) -> int:
        """Queue a NeedDigests for those of `keys` with no digest that no step waits on yet, and return how many `step` now waits on."""
        digests = self._digests
        waiters = self._waiters
        asked = []
        count = 0
        for key in keys:
            if key in digests:
                continue
            count += 1
            waiting = waiters.get(key)
            if waiting is None:
                waiters[key] = [step]
                asked.append(key)
            else:
                waiting.append(step)
        if asked:
            self._events.append(NeedDigests(step, tuple(asked)))
        if count:
            self._pending[step] = count
        return count

    def _check(self, index: int) -> None:
        step = self._steps[index]
        verdict, pending = _decide_from(
            self._unsettled.pop(index, None), step, self._traces.get(index), self._digests
        )
        if isinstance(verdict, list):
            self._states[index] = _State.CHECKING
            if pending is not None:
                self._unsettled[index] = pending
            asked = self._ask(index, verdict)
            assert asked
            return
        self.verdicts[index] = verdict
        if verdict.reason is Reason.CURRENT:
            self._settle(index, _State.CURRENT)
        elif verdict.reason is Reason.INPUT_MISSING:
            assert verdict.key is not None
            self._fail(index, Failed(index, Missing.INPUT, verdict.key))
        else:
            self._inputs[index] = self._pair_digests(step.inputs)
            self._states[index] = _State.STALE
            heapq.heappush(self._stale, index)

    def _complete(self, index: int) -> None:
        """Settle a step that ran, now that every output and found input has a digest."""
        step = self._steps[index]
        digests = self._digests
        status, found = self._finishing.pop(index)
        inputs = self._inputs.pop(index)
        for missing, keys in ((Missing.FOUND, found), (Missing.OUTPUT, step.outputs)):
            for key in keys:
                if digests[key] is None:
                    self._fail(index, Failed(index, missing, key))
                    return
        trace = None
        if status is Status.OK:
            trace = Trace(
                step.digest, inputs, self._pair_digests(step.outputs), self._pair_digests(found)
            )
        self._events.append(Built(index, trace))
        self._settle(index, _State.BUILT)

    def _pair_digests(self, keys: Iterable[Key]) -> tuple[tuple[Key, str], ...]:
        """Return each of `keys`, none of them missing, with its digest."""
        pairs = []
        for key in keys:
            digest = self._digests[key]
            assert digest is not None
            pairs.append((key, digest))
        return tuple(pairs)

    def _fail(self, step: int, event: Failed | None = None) -> None:
        if event is not None:
            self._events.append(event)
        if not self._keep_going:
            self._has_stopped = True
        self._settle(step, _State.FAILED)

    def _settle(self, step: int, state: _State) -> None:
        """Leave `step` in its final `state`, and free the steps that waited on it alone."""
        settled = [(step, state)]
        while settled:
            step, state = settled.pop()
            self._states[step] = state
            for dependent in self._dependents.pop(step, ()):
                if state in _FAILED_STATES:
                    self._doomed.add(dependent)
                self._blockers[dependent] -= 1
                if self._blockers[dependent]:
                    continue
                if dependent in self._doomed:
                    settled.append((dependent, _State.SKIPPED))
                else:
                    self._unblock(dependent)

    def _unblock(self, step: int) -> None:
        if step in self._doomed:
            self._settle(step, _State.SKIPPED)
            return
        self._states[step] = _State.READY
        heapq.heappush(self._ready, step)
