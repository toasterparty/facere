"""Building targets: answering the dependency engine, which decides which rules are stale and in what order, by hashing files and executing recipes on worker threads.

The main thread executes no recipe. It answers the engine until the first rule is stale, then waits on the workers, since only it receives the signals that end a build early.
"""

import contextlib
import enum
import os
import posixpath
import shlex
import threading
import time
from collections.abc import Callable, Container, Iterable
from typing import Literal

from facere import _state
from facere._cache import HashCache, Hashed, Look, Snapshot, iter_listed_files
from facere._collect import Definition, Project
from facere._context import (
    STATE_FILE_NAME,
    Context,
    Recipe,
    calc_path_key,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import (
    Diagnostic,
    FacereError,
    Note,
    format_entering,
    format_error,
    format_leaving,
)
from facere._engine import (
    Built,
    Engine,
    Failed,
    Missing,
    NeedDigests,
    Pause,
    Reason,
    Run,
    Status,
    Trace,
)
from facere._hash import iter_strings
from facere._lock import OutputLock
from facere._observed import Observed
from facere._output import Chunk, Output
from facere._schedule import Crew, Signals
from facere._summary import Summary
from facere._undeclared import ensure_audit_hook

# How long an interrupt waits for the recipes whose commands it killed, before the invocation ends without them.
_INTERRUPT_GRACE_S = 1.0
# How long a stopped task's commands get to end by themselves before they are killed.
_STOP_GRACE_S = 10.0


class _Damage(enum.StrEnum):
    """How an output this invocation built differs from how its rule left it."""

    CHANGED = enum.auto()
    VANISHED = enum.auto()


class _RecipeFailure(Exception):
    """A rule or task failed. `output` holds what its recipe wrote before it did."""

    def __init__(
        self,
        definition: Definition,
        *,
        error: BaseException | None = None,
        reason: str = "",
        notes: tuple[Note, ...] = (),
        output: Iterable[Chunk] = (),
    ) -> None:
        super().__init__(definition.label)
        self.definition = definition
        self.error = error
        self.reason = reason
        self.notes = notes
        self.output = tuple(output)


class _EndedError(Exception):
    """An interrupt or a stop ended a recipe before it finished."""


# Plain classes with slots, since defining a dataclass or a named tuple costs every invocation
# 0.1 to 0.6 ms at import.
class Invocation:
    """What the command line gives a build, and what the build's batches share.

    `collect_cb` loads the project again, `take_lock_cb` takes the output directory's lock unless it is held, and `calc_jobs` returns how many recipes may execute at once. `reached` counts the rules and tasks reached so far, and `built` holds each output this invocation built, with its rule and the hash it left.
    """

    __slots__ = (
        "built",
        "calc_jobs",
        "collect_cb",
        "context",
        "keep_going",
        "lock",
        "reached",
        "signals",
        "start_dir",
        "summary",
        "take_lock_cb",
        "task_args",
    )

    def __init__(
        self,
        *,
        context: Context,
        signals: Signals,
        summary: Summary,
        lock: OutputLock,
        start_dir: str,
        collect_cb: Callable[[], Project],
        take_lock_cb: Callable[[], None],
        calc_jobs: Callable[[], int],
        keep_going: bool,
        task_args: tuple[str, ...] | None,
    ) -> None:
        self.context = context
        self.signals = signals
        self.summary = summary
        self.lock = lock
        self.start_dir = start_dir
        self.collect_cb = collect_cb
        self.take_lock_cb = take_lock_cb
        self.calc_jobs = calc_jobs
        self.keep_going = keep_going
        self.task_args = task_args
        self.reached = 0
        self.built: dict[str, tuple[Definition, str]] = {}

    @property
    def output(self) -> Output:
        """Facere's own streams, which the context holds while a build runs."""
        assert self.context.output is not None
        return self.context.output


class _Target:
    """Something to build: `text` as the command line gave it where `is_typed`, or else an output of a rule, or the name of a task, that was built by default when the invocation started."""

    __slots__ = ("is_path", "is_typed", "text")

    def __init__(self, text: str, is_typed: bool, is_path: bool) -> None:
        self.text = text
        self.is_typed = is_typed
        self.is_path = is_path


def build(invocation: Invocation, project: Project, targets: list[str]) -> None:
    """Build `targets` in order, or when it is empty the defaults, else every rule: each run of rules among them together, then the task that follows them, loading the project again after each task that more targets follow.

    A failure is printed as it happens and counted in the summary. Raises FacereError where a target or the arguments after `--` are in error, before anything executes, and KeyboardInterrupt on an interrupt, once every running command is killed.
    """
    context = invocation.context
    pending = _plan(project, context.root, targets)
    resolved = [found for target in pending for found in _resolve(project, context.root, target)]
    _validate_task_args(resolved, invocation.task_args)
    ensure_audit_hook()
    while True:
        rules, task, pending = _take_batch(project, context.root, pending)
        builder = _Builder(invocation, project)
        can_continue = builder.build(rules, task, pending)
        if not (pending and can_continue):
            break
        invocation.take_lock_cb()
        project = invocation.collect_cb()
    if can_continue and not invocation.summary.failed and invocation.lock.is_held:
        builder.validate_built_intact()


def _validate_task_args(resolved: list[Definition], task_args: tuple[str, ...] | None) -> None:
    """Raise unless `task_args`, the arguments after `--`, are None or empty, or a task among the `resolved` targets takes fac.Args to receive them."""
    if not bool(task_args):
        return
    tasks = list(dict.fromkeys(definition for definition in resolved if definition.is_task))
    if any(task.args_slot is not None for task in tasks):
        return
    if not tasks:
        raise FacereError(
            Diagnostic(
                None,
                "-- passes arguments to the tasks among the targets, which name none",
            )
        )
    first, *others = tasks
    raise FacereError(
        Diagnostic(
            first.location,
            f"{first.label} takes no arguments, and -- passes some",
            tuple(Note(task.location, f"{task.label} takes none either") for task in others),
        )
    )


def _format_failure(failure: _RecipeFailure, start_dir: str) -> list[Chunk]:
    """Return what a failure prints: what its recipe wrote, the failing command or exception with the command's captured stderr and stdout, then the line naming the rule or task."""
    import subprocess

    chunks: list[Chunk] = list(failure.output)
    error = failure.error
    if isinstance(error, subprocess.CalledProcessError | subprocess.TimeoutExpired):
        if isinstance(error, subprocess.TimeoutExpired):
            status = f"timed out after {error.timeout:g} seconds"
        elif error.returncode < 0:
            status = f"was killed by signal {-error.returncode}"
        else:
            status = f"exited with status {error.returncode}"
        command = (
            shlex.join(str(arg) for arg in error.cmd)
            if isinstance(error.cmd, list | tuple)
            else str(error.cmd)
        )
        chunks.append((True, f"fac: command {status}: {command}\n"))
        shown: list[Chunk] = [(True, _to_bytes(error.stderr)), (False, _to_bytes(error.output))]
        cwd = getattr(error, "cwd", None)
        if isinstance(cwd, str) and any(data for _, data in shown):
            shown = [
                (True, f"{format_entering(cwd)}\n"),
                *shown,
                (True, f"{format_leaving(cwd)}\n"),
            ]
        chunks.extend(shown)
    elif error is not None:
        chunks.append((True, _format_exception(error)))
    message = f"{failure.definition.label} failed" + (
        f": {failure.reason}" if failure.reason else ""
    )
    located = FacereError(Diagnostic(failure.definition.location, message, failure.notes))
    chunks.append((True, "".join(f"{line}\n" for line in format_error(located, start_dir))))
    return chunks


def _plan(project: Project, root: str, targets: list[str]) -> list[_Target]:
    """Return `targets` as typed, or the default ones, raising FacereError for each typed one that resolves to nothing."""
    if not targets:
        definitions = project.definitions
        defaults = [definition for definition in definitions if definition.is_default]
        chosen = defaults or [definition for definition in definitions if not definition.is_task]
        return [
            _Target(definition.name, False, False)
            if definition.is_task
            else _Target(definition.outputs[0], False, True)
            for definition in chosen
        ]
    planned = [_Target(target, True, "/" in target or "\\" in target) for target in targets]
    unknown = [target.text for target in planned if not _resolve(project, root, target)]
    if unknown:
        listed = ", ".join(repr(target) for target in unknown)
        names = ", ".join(sorted(project.by_name))
        notes = (Note(None, f"names: {names}"),) if names else ()
        raise FacereError(Diagnostic(None, f"unknown target {listed}", notes))
    return planned


def _resolve(project: Project, root: str, target: _Target) -> list[Definition]:
    """Return the definitions `target` names in `project`, which are none where a default target is gone since the project was first loaded."""
    if not target.is_path:
        found = project.by_name.get(target.text, [])
        return found if target.is_typed else [task for task in found if task.is_task]
    path = target.text.replace("\\", "/") if target.is_typed else target.text
    step = project.graph.producers.get(normalize(path, root))
    return [] if step is None else [project.definitions[step]]


def _take_batch(
    project: Project, root: str, pending: list[_Target]
) -> tuple[list[Definition], Definition | None, list[_Target]]:
    """Return the rules the leading targets of `pending` name, the task that ends their run, if any, and the targets after it.

    Raises FacereError for a typed target that resolves to nothing in `project`, as one may once a task changed what a fac.py defines.
    """
    typed = [target.text for target in pending if target.is_typed]
    if typed:
        _plan(project, root, typed)
    rules: list[Definition] = []
    for index, target in enumerate(pending):
        for definition in _resolve(project, root, target):
            if definition.is_task:
                return rules, definition, pending[index + 1 :]
            rules.append(definition)
    return rules, None, []


def _remove_shadowed(
    context: Context,
    state_path: str,
    records: dict[tuple[str, ...], _state.Record],
    saved_listing: frozenset[str],
    new_outputs: frozenset[str],
) -> dict[tuple[str, ...], _state.Record]:
    """Forget each record that names a file name a file new since the last invocation has, or an output no rule declared then, whether or not this invocation's targets reach its rule, and return the records left."""
    if not _state.has_added_names(records):
        return records
    listing = frozenset(iter_listed_files(context.out_dir))
    if listing == saved_listing and not new_outputs:
        return records
    shadowed = _find_shadowed(records, (listing - saved_listing) | new_outputs)
    _state.remove(state_path, shadowed)
    if listing != saved_listing:
        _state.save_listing(state_path, listing)
    return {key: record for key, record in records.items() if key not in shadowed}


def _calc_names(paths: Iterable[str]) -> frozenset[str]:
    return frozenset(calc_path_key(posixpath.basename(path)) for path in paths)


def _find_shadowed(
    records: dict[tuple[str, ...], _state.Record], new_paths: Iterable[str]
) -> list[tuple[str, ...]]:
    """Return the key of each record naming the file name of one of `new_paths`."""
    new_names = _calc_names(new_paths)
    return [key for key, record in records.items() if not new_names.isdisjoint(record.added_names)]


def _find_within(paths: set[str], outputs: Iterable[str], dirs: Container[str]) -> set[str]:
    """Return those of `paths` that are one of `outputs` or lie in one of them that is among `dirs`, the directories a session walked."""
    exact = paths.intersection(outputs)
    prefixes = tuple(f"{path}/" for path in exact if path in dirs)
    if not prefixes:
        return exact
    return exact | {path for path in paths if path.startswith(prefixes)}


def _to_bytes(data: bytes | str | None) -> bytes:
    if data is None:
        return b""
    return data if isinstance(data, bytes) else data.encode("utf-8", "surrogateescape")


def _format_exception(error: BaseException) -> str:
    import traceback

    package_dir = os.path.dirname(__file__)
    report = traceback.TracebackException.from_exception(error)
    report.stack = traceback.StackSummary.from_list(
        [frame for frame in report.stack if os.path.dirname(frame.filename) != package_dir]
    )
    return "".join(report.format())


class _Start:
    """What a worker takes with it, as it is handed a stale rule, from the tables only the mutex guards.

    `position` places the rule among those reached. `record` is the rule's last success, if any. `inputs_built` holds each output this batch built that the rule inputs or is ordered after, with its rule and the hash it left. `shadow_mark` counts the new files' names seen before the rule started.
    """

    __slots__ = ("inputs_built", "position", "record", "rule", "shadow_mark")

    def __init__(
        self,
        rule: Definition,
        position: int,
        record: _state.Record | None,
        inputs_built: tuple[tuple[str, Definition, str], ...],
        shadow_mark: int,
    ) -> None:
        self.rule = rule
        self.position = position
        self.record = record
        self.inputs_built = inputs_built
        self.shadow_mark = shadow_mark


class _Finished:
    """A rule whose recipe succeeded, until the engine has its outputs' hashes: its recipe, the inputs that moved under it, and its shadow mark."""

    __slots__ = ("moved", "recipe", "shadow_mark")

    def __init__(self, recipe: Recipe, moved: tuple[str, ...], shadow_mark: int) -> None:
        self.recipe = recipe
        self.moved = moved
        self.shadow_mark = shadow_mark


class _GiveRequest:
    """A task's request that the main thread give the output directory's lock, and the main thread's answer."""

    __slots__ = ("answered", "is_requested", "refusal")

    def __init__(self) -> None:
        self.is_requested = False
        self.answered = threading.Event()
        self.refusal: str | None = None


class _Builder:
    """The host of the dependency engine for one batch, in which a key is a path as normalize returns it.

    A batch is one engine session over the state as the batch found it: the rules among consecutive targets, then the task that follows them. A task may change any file, so what follows it is another batch, checked afresh, as a second invocation would.

    Every worker runs one loop: take the mutex, poll the engine, give the mutex back while hashing or executing, and take it again to answer. The mutex guards the engine and every table below it, and is never held across a read, a write, or a recipe. State writes take turns under a lock of their own.
    """

    def __init__(self, invocation: Invocation, project: Project) -> None:
        self.invocation = invocation
        self.context = context = invocation.context
        self.project = project
        self.state_path = posixpath.join(context.state_dir, STATE_FILE_NAME)
        self.steps = {definition: step for step, definition in enumerate(project.definitions)}
        self.steps_by_key = {
            _state.calc_key(definition.outputs): step
            for definition, step in self.steps.items()
            if not definition.is_task
        }
        state = _state.load(self.state_path)
        self.output_keys = frozenset(project.producers_by_key)
        self.saved_declared = state.declared
        new_outputs = (
            self.output_keys - state.declared if state.declared is not None else frozenset()
        )
        declared = self.steps_by_key.keys()
        try:
            stale_keys = [key for key in {*state.records, *state.moved} if key not in declared]
            _state.remove(self.state_path, stale_keys)
            records = {key: record for key, record in state.records.items() if key in declared}
            self.records = _remove_shadowed(
                context, self.state_path, records, state.listing, new_outputs
            )
        except OSError as error:
            raise FacereError(Diagnostic(None, f"{error}")) from error
        self.moved = state.moved
        self.cache = HashCache(state.hashes, time.time_ns())
        self.producers = project.graph.producers
        self.crew = Crew(invocation.calc_jobs)
        self._mutex = threading.Lock()
        self._wake = threading.Condition(self._mutex)
        self._idle = 0
        self._state_lock = threading.Lock()
        self._snapshot_lock = threading.Lock()
        self._snapshot: Snapshot | None = None
        self.running: dict[int, Definition] = {}
        # Each rule that executed and awaits its Built.
        self.finishing: dict[int, _Finished] = {}
        # The rules that executed and wrote every output.
        self.succeeded: set[int] = set()
        self.total = 0
        # How many of the session's verdicts `invocation.reached` counts.
        self.counted = 0
        self.failed = 0
        self.has_executed = False
        # The outputs this batch built, each a key of `invocation.built`.
        self.built: set[str] = set()
        # The names of the files found new in a directory output, a set per walk that found some.
        self.shadows: list[frozenset[str]] = []
        # The paths the session asked the hash of and found nothing at, for a watch.
        self.absent: set[str] = set()
        self.unsettled: list[tuple[int, Diagnostic]] = []
        self.ended: list[tuple[int, Diagnostic]] = []
        # By a path key's prefix up to its last slash, the rule outputting that directory or one holding it.
        self.holders: dict[str, Definition | None] = {}
        self._is_interrupted = False
        self._is_aborted = False
        self._crash: BaseException | None = None
        invocation.built = {
            path: built for path, built in invocation.built.items() if path in self.producers
        }
        self.engine = Engine(
            project.graph, keep_going=invocation.keep_going, pool_sizes=project.pool_sizes
        )
        self._load_traces()

    def build(
        self, rules: list[Definition], task: Definition | None, pending: list[_Target]
    ) -> bool:
        """Bring `rules` up to date together, then execute `task`, if any, once the rules it inputs are too, and return whether the invocation may go on to the `pending` targets."""
        steps = [self.steps[rule] for rule in rules]
        upstream = () if task is None else self.project.graph.upstream[self.steps[task]]
        self._plan_total([*steps, *upstream], task, pending)
        try:
            self._build_steps([*steps, *upstream])
            if task is not None and self._can_execute(upstream):
                self._run_task(task)
        except KeyboardInterrupt:
            self._interrupt()
            raise
        finally:
            summary = self.invocation.summary
            summary.unsettled.extend(diagnostic for _, diagnostic in sorted(self.unsettled))
            summary.ended.extend(diagnostic for _, diagnostic in sorted(self.ended))
            self.unsettled.clear()
            self.ended.clear()
            self.commit()
        return self._can_go_on()

    def commit(self) -> None:
        """Save what the batch learned beyond its records, while the invocation holds the lock: the tree as it leaves it, so a file its recipes wrote never counts as new, the hash cache, and the outputs declared. Losing any of them costs only rebuilds and reads."""
        if not self.invocation.lock.is_held:
            return
        observed = self.context.observed
        with self._state_lock, contextlib.suppress(OSError):
            if observed is not None:
                self._add_observed(observed)
            if self.has_executed and _state.has_added_names(self.records):
                listing = frozenset(iter_listed_files(self.context.out_dir))
                _state.save_listing(self.state_path, listing)
            _state.save_hashes(self.state_path, self.cache.take_changes(is_final=True))
            if self.output_keys != self.saved_declared:
                _state.save_declared(self.state_path, self.output_keys)
                self.saved_declared = self.output_keys
            if observed is not None:
                observed.save(self.state_path)

    def _add_observed(self, observed: Observed) -> None:
        """Add to `observed` what the session saw, noting which paths lie in a declared output, then hash the files collection opened."""
        files = self.cache.get_seen_files()
        dirs = self.cache.get_listed()
        with self._mutex:
            absent = set(self.absent)
            failed = [
                step
                for step, verdict in self.engine.verdicts.items()
                if verdict.reason is not Reason.CURRENT and step not in self.succeeded
            ]
        paths = {*files, *dirs, *absent}
        outputs = _find_within(paths, self.producers, dirs)
        failed_outputs = [
            output for step in failed for output in self.project.definitions[step].outputs
        ]
        observed.add(files, dirs, absent, outputs, _find_within(outputs, failed_outputs, dirs))
        observed.resolve_reads(self.cache)

    def validate_built_intact(self) -> None:
        """Fail the first output this invocation built whose content changed after its rule finished, which only an undeclared write explains. One that vanished passes, since the next invocation rebuilds it."""
        failure = self._find_damaged()
        if failure is not None:
            self._report(failure)

    def _load_traces(self) -> None:
        """Give the engine each record's trace, ordering its rule after the rule that outputs each path it found, a directory holding one, or a path differing from one only in case."""
        unheld: set[str] = set()
        for key, record in self.records.items():
            follows = []
            for path, _ in record.trace.found:
                producer = None if path in unheld else self._find_producer(path)
                if producer is None:
                    unheld.add(path)
                else:
                    follows.append(producer.outputs[0])
            self.engine.load_trace(self.steps_by_key[key], record.trace, follows)

    def _interrupt(self) -> None:
        """Kill every running command, leave every executing rule unrecorded, and note each recipe this ended."""
        self.context.commands.kill()
        with self._mutex:
            self._is_interrupted = True
            self.engine.stop()
            running = sorted(self.running.items())
            self._notify()
        self.invocation.summary.ended.extend(
            Diagnostic(definition.location, f"interrupted {definition.label}")
            for _, definition in running
        )
        deadline_s = time.monotonic() + _INTERRUPT_GRACE_S
        with contextlib.suppress(KeyboardInterrupt):
            self.crew.wait(lambda: time.monotonic() < deadline_s)

    def _plan_total(
        self, steps: list[int], task: Definition | None, pending: list[_Target]
    ) -> None:
        """Count what the invocation will have reached once the `pending` targets are built too, as far as the project now loaded tells."""
        root = self.context.root
        self.total = self.invocation.reached + len(self.engine.find_closure(steps))
        while task is not None:
            self.total += 1
            rules, task, pending = _take_batch(self.project, root, pending)
            later = [self.steps[rule] for rule in rules]
            if task is not None:
                later.extend(self.project.graph.upstream[self.steps[task]])
            self.total += len(self.engine.find_closure(later))

    def _can_go_on(self) -> bool:
        if self.invocation.signals.is_stop_requested or self._is_aborted:
            return False
        return self.invocation.keep_going or not self.failed

    def _can_execute(self, upstream: Iterable[int]) -> bool:
        """Say whether a task may execute, whose rules `upstream` must each have been found current or built."""
        if not self._can_go_on():
            return False
        verdicts = self.engine.verdicts
        return all(
            step in self.succeeded or (step in verdicts and verdicts[step].reason is Reason.CURRENT)
            for step in upstream
        )

    def _build_steps(self, steps: Iterable[int]) -> None:
        """Bring `steps` up to date by answering the engine's events until it has none."""
        with self._mutex:
            self.engine.request(steps)
        try:
            first = self._work(None, is_main=True)
            if first is not None:
                self._add_worker(first)
                self.crew.wait(self._on_wake)
            if self._crash is not None:
                raise self._crash
        finally:
            with self._mutex:
                self._count_checked()

    def _on_wake(self) -> bool:
        """Stop the engine once a signal asked for a graceful stop, so the rules executing finish and no other starts."""
        if self.invocation.signals.is_stop_requested:
            with self._mutex:
                self.engine.stop()
                self._notify()
        return True

    def _guard(self, work: Callable[[], None]) -> None:
        """Call `work` on a worker thread, and keep whatever it raises, a bug of Facere's own, for the main thread to raise."""
        try:
            work()
        except BaseException as error:  # noqa: BLE001 - the main thread raises it
            with self._mutex:
                self._crash = self._crash or error
                self.engine.stop()
                self._notify()

    def _work(self, first: Run | None, *, is_main: bool = False) -> Run | None:
        """Answer the engine's events, starting with `first`, until it has none.

        The main thread executes no recipe, so where `is_main` the first Run handed out is returned unanswered instead, for a worker to start with.
        """
        signals = self.invocation.signals
        engine = self.engine
        while True:
            with self._mutex:
                # Read here too, since the main thread reads it only each time its wait wakes.
                if signals.is_stop_requested:
                    engine.stop()
                event = first or self._poll()
                first = None
                if event is Pause.DONE:
                    self._notify()
                    return None
                start = None
                if type(event) is Run:
                    if is_main:
                        return event
                    start = self._start(event.step)
            if start is not None:
                self._run(event.step, start)
                continue
            try:
                if type(event) is NeedDigests:
                    self._observe(event.keys)
                elif type(event) is Built:
                    self._record(event.step, event.trace)
                else:
                    assert type(event) is Failed
                    self._answer_failed(event)
            except OSError as error:
                rule = self.project.definitions[event.step]
                self._abort(event.step, _RecipeFailure(rule, reason=f"{error}"))

    def _notify(self) -> None:
        """Wake the workers waiting for an event, after an answer. Call it with the mutex held."""
        if self._idle:
            self._wake.notify_all()

    def _add_worker(self, first: Run | None = None) -> None:
        """Start a worker, unless as many as may execute at once already do."""

        def work() -> None:
            self._work(first)

        self.crew.try_add(lambda: self._guard(work))

    def _poll(self) -> Run | NeedDigests | Built | Failed | Literal[Pause.DONE]:
        """Return the engine's next event, waiting with the mutex given back while other workers hold what everything left waits on."""
        while True:
            if self._crash is not None:
                return Pause.DONE
            event = self.engine.poll()
            if event is Pause.DONE or not isinstance(event, Pause):
                return event
            # An event no worker could answer leaves the engine waiting on it for good.
            if self._is_aborted and not self.running and not self.finishing:
                return Pause.DONE
            self._idle += 1
            self._wake.wait()
            self._idle -= 1

    def _start(self, step: int) -> _Start:
        """Count the stale rule at `step` as executing, and start another worker unless one is waiting for work."""
        rule = self.project.definitions[step]
        graph = self.project.graph
        built = self.invocation.built
        inputs_built = tuple(
            (output, *built[output])
            for output in (*graph.steps[step].inputs, *graph.steps[step].order_only)
            if output in self.built
        )
        position = self.invocation.reached + len(self.engine.verdicts) - self.counted
        self.running[step] = rule
        self.has_executed = True
        if not self._idle:
            self._add_worker()
        record = self.records.get(_state.calc_key(rule.outputs))
        return _Start(rule, position, record, inputs_built, len(self.shadows))

    def _count_checked(self) -> None:
        """Count the rules checked since the last count, which holds even when a failure or an interrupt ends the build."""
        checked = list(self.engine.verdicts.items())[self.counted :]
        self.counted += len(checked)
        self.invocation.reached += len(checked)
        self.invocation.summary.outputs_current += sum(
            len(self.project.definitions[step].outputs)
            for step, verdict in checked
            if verdict.reason is Reason.CURRENT
        )

    def _answer_failed(self, event: Failed) -> None:
        with self._mutex:
            self.finishing.pop(event.step, None)
            self._notify()
        self._fail(self._build_missing_failure(event))

    def _observe(self, paths: Iterable[str]) -> None:
        """Tell the engine the hash of what is at each of `paths`: of an output read afresh, and of any other path as the session first saw it."""
        new_files: list[str] = []
        producers = self.producers
        fetch = self.cache.fetch
        built: list[tuple[str, Hashed]] = []
        digests: dict[str, str | None] = {}
        for path in paths:
            if path not in producers:
                hashed = fetch(path)
            else:
                hashed = fetch(path, Look.AGAIN, new_files)
                if hashed is not None:
                    built.append((path, hashed))
            digests[path] = None if hashed is None else hashed.digest
        shadowed: list[tuple[str, ...]] = []
        with self._mutex:
            if self.context.observed is not None:
                self.absent.update(path for path, digest in digests.items() if digest is None)
            if new_files:
                shadowed = self._forget_shadowed(new_files)
            for path, hashed in built:
                step = producers[path]
                if step in self.finishing:
                    self.built.add(path)
                    self.invocation.built[path] = (self.project.definitions[step], hashed.digest)
            self.engine.give_digests(digests)
            self._notify()
        self._remove_saved(shadowed)

    def _forget_shadowed(self, new_files: list[str]) -> list[tuple[str, ...]]:
        """Forget at once each record a file new in a directory output shadows, and return their keys, to forget in the saved state too. A rule executing now is judged against the names as it is recorded."""
        self.shadows.append(_calc_names(new_files))
        shadowed = _find_shadowed(self.records, new_files)
        for key in shadowed:
            del self.records[key]
            self.engine.forget_trace(self.steps_by_key[key])
        return shadowed

    def _remove_saved(self, keys: list[tuple[str, ...]]) -> None:
        if keys:
            with self._state_lock:
                _state.remove(self.state_path, keys)

    def _run(self, step: int, start: _Start) -> None:
        """Execute the recipe of the stale rule at `step`, and tell the engine how it ended and what it reported."""
        try:
            recipe, moved = self._execute_rule(step, start)
        except _RecipeFailure as failure:
            self._fail(failure, step)
            return
        except OSError as error:
            self._fail(_RecipeFailure(start.rule, reason=f"{error}"), step)
            return
        except _EndedError:
            with self._mutex:
                del self.running[step]
                self.engine.finish(step, Status.FAILED)
                self._notify()
            return
        self.invocation.output.write(recipe.output)
        with self._mutex:
            del self.running[step]
            if self._is_interrupted:
                # A recipe that outlived the interrupt's kill saw its commands die, so nothing of it is kept.
                self.engine.finish(step, Status.FAILED)
            else:
                self.finishing[step] = _Finished(recipe, moved, start.shadow_mark)
                status = Status.UNSETTLED if moved else Status.OK
                self.engine.finish(step, status, sorted(recipe.reported))
            self._notify()

    def _execute_rule(self, step: int, start: _Start) -> tuple[Recipe, tuple[str, ...]]:
        """Execute the rule's recipe and return it with the inputs that moved under it."""
        rule = start.rule
        self._validate_inputs_intact(start)
        before = {path: self.cache.fetch(path) for path in rule.inputs}
        if start.record is not None:
            self._remove_saved([_state.calc_key(rule.outputs)])
            before.update((path, self.cache.fetch(path)) for path, _ in start.record.trace.found)
        for output in rule.outputs:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        self._announce(rule, start.position)
        snapshot = self._ensure_snapshot()
        recipe = self._execute(rule)
        with self._mutex:
            producers = {path: self._find_producer(path) for path in recipe.reported}
        for path in sorted(recipe.reported):
            self._validate_ordered(step, path, producers[path], recipe)
        return recipe, self._find_moved_inputs(recipe, before, producers, snapshot)

    def _ensure_snapshot(self) -> Snapshot:
        """Return the snapshot, taken before the session's first recipe starts, since every worker asks for it first."""
        with self._snapshot_lock:
            if self._snapshot is None:
                self._snapshot = Snapshot(self.cache, self.context.out_dir)
            return self._snapshot

    def _record(self, step: int, trace: Trace | None) -> None:
        """Save the `trace` of the rule at `step`, which executed and wrote every output, or where it must stay stale, the inputs that moved."""
        rule = self.project.definitions[step]
        key = _state.calc_key(rule.outputs)
        with self._mutex:
            finished = self.finishing.pop(step)
            recipe, moved, shadow_mark = finished.recipe, finished.moved, finished.shadow_mark
            self.succeeded.add(step)
            self.invocation.summary.rules_run += 1
            # A file found new while the recipe executed may shadow one it read, and its tool may have searched before or after.
            is_shadowed = any(
                not names.isdisjoint(recipe.reported_names) for names in self.shadows[shadow_mark:]
            )
            record = None
            if trace is not None and not is_shadowed:
                record = self.records[key] = _state.Record(
                    trace, tuple(sorted(recipe.reported_names))
                )
                self.moved.pop(key, None)
            else:
                self._leave_unrecorded(step, rule, key, moved)
            self._notify()
        with self._state_lock:
            changes = self.cache.take_changes()
            if record is not None:
                _state.save(self.state_path, key, record, changes)
            else:
                _state.save_moved(self.state_path, key, moved, changes)

    def _leave_unrecorded(
        self, step: int, rule: Definition, key: tuple[str, ...], moved: tuple[str, ...]
    ) -> None:
        """Leave `rule` stale, keeping the inputs that `moved`, and warn where one of them also changed during the rule's last execution, since a rule whose own tool changes its input never settles."""
        self.records.pop(key, None)
        repeated = [path for path in moved if path in self.moved.get(key, ())]
        if repeated:
            message = f"{rule.label} stays stale: {repeated[0]} changed while its recipe executed, in this execution and its last"
            self.unsettled.append((step, Diagnostic(rule.location, message)))
        self.moved[key] = moved

    def _build_missing_failure(self, event: Failed) -> _RecipeFailure:
        rule = self.project.definitions[event.step]
        if event.missing is Missing.INPUT:
            return _RecipeFailure(rule, reason=f"its input {event.key} is missing")
        if event.missing is Missing.FOUND:
            reason = f"its recipe reported reading {event.key}, which it then removed"
            return _RecipeFailure(rule, reason=reason)
        missing = [
            output for output in _state.calc_key(rule.outputs) if self.cache.fetch(output) is None
        ]
        reason = f"its recipe succeeded without writing {', '.join(missing or [event.key])}"
        return _RecipeFailure(rule, reason=reason)

    def _fail(self, failure: _RecipeFailure, running_step: int | None = None) -> None:
        """Print `failure` and count it, telling the engine where the rule at `running_step` was executing."""
        if not self._is_interrupted:
            self._report(failure)
        if running_step is None:
            return
        with self._mutex:
            del self.running[running_step]
            self.engine.finish(running_step, Status.FAILED)
            self._notify()

    def _abort(self, step: int, failure: _RecipeFailure) -> None:
        """Print `failure`, which left the engine an event about `step` that no worker can answer, and end the session once the rules executing finish."""
        self._report(failure)
        with self._mutex:
            self.finishing.pop(step, None)
            self._is_aborted = True
            self.engine.stop()
            self._notify()

    def _report(self, failure: _RecipeFailure) -> None:
        with self._mutex:
            self.failed += 1
            self.invocation.summary.failed += 1
        self.invocation.output.write(_format_failure(failure, self.invocation.start_dir))

    def _validate_inputs_intact(self, start: _Start) -> None:
        """Fail the rule without executing it where an output this batch built, which it inputs or is ordered after, changed or vanished since its rule finished.

        Other recipes execute meanwhile, so this vouches only for the moment the recipe starts. A change after it leaves the rule unrecorded, as any input changed during a recipe does, and fails the invocation as it ends.
        """
        for output, producer, digest in start.inputs_built:
            damage = self._find_damage(output, digest)
            if damage is not None:
                raise _RecipeFailure(
                    start.rule,
                    reason=f"its input {output} {damage} after {producer.label} finished",
                    notes=(Note(producer.location, f"{producer.label} outputs {output}"),),
                )

    def _find_damage(self, output: str, digest: str) -> _Damage | None:
        """Return how `output` differs from the content with hash `digest` that its rule left, or None where it doesn't."""
        current = self.cache.fetch(output, Look.CHECK)
        if current is None:
            return _Damage.VANISHED
        return _Damage.CHANGED if current.digest != digest else None

    def _find_damaged(self) -> _RecipeFailure | None:
        """Return the failure of the first output this invocation built whose content changed after its rule finished, noting the others."""
        damaged = [
            (output, rule)
            for output, (rule, digest) in self.invocation.built.items()
            if self._find_damage(output, digest) is _Damage.CHANGED
        ]
        if not damaged:
            return None
        (output, rule), *others = damaged
        notes = tuple(
            Note(other.location, f"{other_output}, which {other.label} output, changed too")
            for other_output, other in others
        )
        reason = f"its output {output} changed after it finished"
        return _RecipeFailure(rule, reason=reason, notes=notes)

    def _find_moved_inputs(
        self,
        recipe: Recipe,
        before: dict[str, Hashed | None],
        producers: dict[str, Definition | None],
        snapshot: Snapshot,
    ) -> tuple[str, ...]:
        """Return the inputs that changed while the recipe executed, even where the content changed back, so recording the rule would claim it current for files its tool never read.

        `before` holds what the engine was told of each declared input and each found input in the rule's record. A file first reported has none, since its tool read it before the recipe could report it, so it compares with the snapshot, or where a rule outputs it, with what the engine was told of it, unless the recipe wrote it in Python itself. Each comparison leaves what the session saw as it is, since other recipes compare against it at the same time.
        """
        moved = {
            path for path, hashed in before.items() if self.cache.fetch(path, Look.CHECK) != hashed
        }
        for path in recipe.reported - before.keys():
            if calc_path_key(path) in recipe.written:
                continue
            if producers[path] is not None:
                has_moved = self.cache.has_moved(path)
            else:
                has_moved = snapshot.has_moved(path)
            if has_moved:
                moved.add(path)
        return tuple(sorted(moved))

    def _validate_ordered(
        self, step: int, path: str, producer: Definition | None, recipe: Recipe
    ) -> None:
        """Fail the rule at `step`, whose recipe reported reading `path`, which `producer` outputs, unless it declares an input that orders it after that rule."""
        rule = self.project.definitions[step]
        if producer is None or producer is rule:
            return
        if self.steps[producer] in self.project.graph.upstream[step]:
            return
        raise _RecipeFailure(
            rule,
            reason=f"its recipe reported reading {path}, though no fac.Input or fac.OrderOnly parameter orders it after the rule that outputs it",
            notes=(Note(producer.location, f"{producer.label} outputs {path}"),),
            output=recipe.output,
        )

    def _find_producer(self, path: str) -> Definition | None:
        """Return the rule that outputs `path`, or a directory holding it. Call it with the mutex held, or before any worker starts."""
        producers_by_key = self.project.producers_by_key
        key = calc_path_key(path)
        if key in producers_by_key:
            return producers_by_key[key]
        prefix = key[: key.rfind("/") + 1]
        if prefix not in self.holders:
            self.holders[prefix] = next(
                (
                    producers_by_key[ancestor]
                    for ancestor in iter_self_and_parents(posixpath.dirname(key))
                    if ancestor in producers_by_key
                ),
                None,
            )
        return self.holders[prefix]

    def _announce(self, definition: Definition, position: int) -> None:
        self.invocation.output.show_status(f"[{position}/{self.total}] {definition.label}")

    def _build_recipe(self, definition: Definition) -> Recipe:
        root = self.context.root
        data_paths = {
            calc_path_key(normalize(text, root))
            for value in definition.text_values.values()
            for text in iter_strings(value)
            if text
        }
        return Recipe(
            is_task=definition.is_task,
            tracked=frozenset(map(calc_path_key, (*definition.inputs, *definition.outputs))),
            order_only=frozenset(map(calc_path_key, definition.order_only)),
            exempt=frozenset(data_paths),
            shared_modules=self.project.shared_modules,
            output_keys=self.project.producers_by_key.keys(),
        )

    def _execute(self, definition: Definition, task_args: tuple[str, ...] | None = None) -> Recipe:
        """Call the recipe of `definition` on this thread, raising _RecipeFailure where it fails, and _EndedError where an interrupt or a stop ended it."""
        args, kwargs = definition.calc_call(task_args)
        recipe = self._build_recipe(definition)
        try:
            with self.context.executing(recipe):
                definition.fn(*args, **kwargs)
        except BaseException as error:  # noqa: BLE001 - whatever a recipe raises fails it
            is_ended = self.context.commands.is_ended(definition.is_task)
            if isinstance(error, KeyboardInterrupt) and is_ended:
                raise _EndedError from None
            if recipe.undeclared is None and recipe.misuse is None:
                raise _RecipeFailure(definition, error=error, output=recipe.output) from error
        if recipe.misuse is not None:
            raise _RecipeFailure(definition, reason=recipe.misuse, output=recipe.output)
        if recipe.undeclared is not None:
            path, reason = recipe.undeclared
            with self._mutex:
                producer = self._find_producer(path)
            notes = (
                (Note(producer.location, f"{producer.label} outputs {path}"),) if producer else ()
            )
            raise _RecipeFailure(definition, reason=reason, notes=notes, output=recipe.output)
        return recipe

    def _run_task(self, task: Definition) -> None:
        """Execute `task` alone on a thread of its own, giving the lock on its request, and on a graceful stop asking its commands to end, then killing them."""
        invocation = self.invocation
        commands = self.context.commands
        step = self.steps[task]
        invocation.reached += 1
        self._announce(task, invocation.reached)
        self.has_executed = True
        give = _GiveRequest()
        failures: list[_RecipeFailure | _EndedError] = []
        kill_at_s: float | None = None

        def work() -> None:
            try:
                self._execute(task, invocation.task_args)
            except (_RecipeFailure, _EndedError) as failure:
                failures.append(failure)

        def request_give() -> None:
            if not give.is_requested:
                give.is_requested = True
                self.crew.wake()
            give.answered.wait()
            if give.refusal is not None:
                raise RuntimeError(give.refusal)

        def on_wake() -> bool:
            nonlocal kill_at_s
            if give.is_requested and not give.answered.is_set():
                self._give_lock(give)
            if not invocation.signals.is_stop_requested:
                return True
            now_s = time.monotonic()
            if kill_at_s is None:
                commands.stop_tasks()
                kill_at_s = now_s + _STOP_GRACE_S
            elif now_s >= kill_at_s:
                commands.kill()
            # A recipe that outlives its killed commands is left behind.
            return now_s < kill_at_s + _INTERRUPT_GRACE_S

        if self.context.observed is not None:
            missing = [path for path in task.inputs if self.cache.fetch(path) is None]
            with self._mutex:
                self.absent.update(missing)
            # A task may never end, so the watch learns now what to wait on.
            self.commit()
        with self._mutex:
            self.running[step] = task
        self.context.give_lock_cb = request_give
        try:
            self.crew.try_add(lambda: self._guard(work))
            has_ended = self.crew.wait(on_wake)
        finally:
            self.context.give_lock_cb = None
        with self._mutex:
            del self.running[step]
        if self._crash is not None:
            raise self._crash
        failure = failures[0] if failures else None
        # On Windows the console can end a task's commands before this thread wakes to ask them to.
        if (
            not has_ended
            or isinstance(failure, _EndedError)
            or (failure is not None and invocation.signals.is_stop_requested)
        ):
            self.ended.append((step, Diagnostic(task.location, f"stopped {task.label}")))
        elif failure is not None:
            self._report(failure)
        else:
            invocation.summary.tasks_run += 1

    def _give_lock(self, give: _GiveRequest) -> None:
        """Answer a task's request for the lock to be given: save the state, then give the lock unless an output this invocation built changed since its rule finished, which no later check could tell from another invocation's rebuild."""
        self.commit()
        damaged = self._find_damaged()
        if damaged is None:
            self.invocation.lock.give()
        else:
            rule = damaged.definition
            give.refusal = (
                f"fac.give_lock keeps the lock, since {rule.label} failed: {damaged.reason}"
            )
        give.answered.set()
