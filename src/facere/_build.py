"""Building targets: answering the dependency engine, which decides which rules are stale and in what order, by hashing files and executing recipes one at a time."""

import contextlib
import enum
import os
import posixpath
import shlex
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from typing import NamedTuple

from facere import _state
from facere._cache import HashCache, Hashed, Snapshot, iter_listed_files
from facere._collect import Definition, Project
from facere._command import write_output
from facere._context import (
    STATE_FILE_NAME,
    Context,
    Recipe,
    calc_path_key,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note, print_error
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
from facere._summary import Summary
from facere._undeclared import ensure_audit_hook


class _Damage(enum.StrEnum):
    """How an output this invocation built differs from how its rule left it."""

    CHANGED = enum.auto()
    VANISHED = enum.auto()


class RecipeFailure(Exception):
    def __init__(
        self,
        definition: Definition,
        *,
        error: BaseException | None = None,
        reason: str = "",
        notes: tuple[Note, ...] = (),
    ) -> None:
        super().__init__(definition.label)
        self.definition = definition
        self.error = error
        self.reason = reason
        self.notes = notes


def resolve_targets(project: Project, root: str, targets: list[str]) -> list[Definition]:
    """Return the definitions `targets` resolve to, in order, or when `targets` is empty the defaults, else every rule."""
    if not targets:
        definitions = project.definitions
        defaults = [definition for definition in definitions if definition.is_default]
        return defaults or [definition for definition in definitions if not definition.is_task]
    resolved: list[Definition] = []
    unknown: list[str] = []
    for target in targets:
        if "/" in target or "\\" in target:
            step = project.graph.producers.get(normalize(target.replace("\\", "/"), root))
            found = [] if step is None else [project.definitions[step]]
        else:
            found = project.by_name.get(target, [])
        resolved.extend(found)
        if not found:
            unknown.append(target)
    if unknown:
        listed = ", ".join(repr(target) for target in unknown)
        names = ", ".join(sorted(project.by_name))
        notes = (Note(None, f"names: {names}"),) if names else ()
        raise FacereError(Diagnostic(None, f"unknown target {listed}", notes))
    return resolved


def validate_task_args(resolved: list[Definition], task_args: tuple[str, ...] | None) -> None:
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


def build(
    context: Context,
    project: Project,
    targets: list[Definition],
    summary: Summary,
    progress_cb: Callable[[str], None],
    task_args: tuple[str, ...] | None = None,
) -> None:
    """Build `targets` in order, `task_args` filling the fac.Args parameter of every task among them, and raise RecipeFailure on the first failure.

    `summary` counts what ran and what was current, and names the definition an interrupt stopped, so it holds the invocation's progress even when this raises. `progress_cb` gets `[position/total] label` as each rule or task starts to execute, where the position counts every rule and task reached, executed or not.
    """
    state_path = posixpath.join(context.state_dir, STATE_FILE_NAME)
    state = _state.load(state_path)
    declared = {
        _state.calc_key(definition.outputs)
        for definition in project.definitions
        if not definition.is_task
    }
    output_keys = frozenset(project.producers_by_key)
    new_outputs = output_keys - state.declared if state.declared is not None else frozenset()
    try:
        stale_keys = [key for key in {*state.records, *state.moved} if key not in declared]
        _state.remove(state_path, stale_keys)
        records = {key: record for key, record in state.records.items() if key in declared}
        records = _remove_shadowed(context, state_path, records, state.listing, new_outputs)
    except OSError as error:
        raise FacereError(Diagnostic(None, f"{error}")) from error
    ensure_audit_hook()
    builder = _Builder(
        context,
        project,
        records,
        state.moved,
        HashCache(state.hashes, time.time_ns()),
        state_path,
        summary,
        progress_cb,
    )
    try:
        builder.build(targets, task_args)
        builder.validate_built_intact()
    finally:
        builder.save_listing()
        builder.save_hashes()
        if output_keys != state.declared:
            with contextlib.suppress(OSError):
                _state.save_declared(state_path, output_keys)


def report_failure(failure: RecipeFailure, start_dir: str) -> None:
    """Print the failing command or exception, with the command's captured stderr and stdout, then name the rule or task."""
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
        print(f"fac: command {status}: {command}", file=sys.stderr, flush=True)
        write_output(_to_bytes(error.stderr), _to_bytes(error.output))
    elif error is not None:
        print(_format_exception(error), end="", file=sys.stderr, flush=True)
    message = f"{failure.definition.label} failed" + (
        f": {failure.reason}" if failure.reason else ""
    )
    print_error(
        FacereError(Diagnostic(failure.definition.location, message, failure.notes)), start_dir
    )


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


def _find_shadowed(
    records: dict[tuple[str, ...], _state.Record], new_paths: Iterable[str]
) -> list[tuple[str, ...]]:
    """Return the key of each record naming the file name of one of `new_paths`."""
    new_names = {calc_path_key(posixpath.basename(path)) for path in new_paths}
    return [key for key, record in records.items() if not new_names.isdisjoint(record.added_names)]


def _to_bytes(data: bytes | str | None) -> bytes:
    if data is None:
        return b""
    return data if isinstance(data, bytes) else data.encode("utf-8", "surrogateescape")


def _format_exception(error: BaseException) -> str:
    package_dir = os.path.dirname(__file__)
    report = traceback.TracebackException.from_exception(error)
    report.stack = traceback.StackSummary.from_list(
        [frame for frame in report.stack if os.path.dirname(frame.filename) != package_dir]
    )
    return "".join(report.format())


class _Session(NamedTuple):
    """What one engine builds: the steps of a run of rules among the targets, then the task that follows them, if any."""

    rules: list[int]
    task: Definition | None


class _Builder:
    """The host of the dependency engine for one invocation, in which a key is a path as normalize returns it.

    A session is one engine: it lasts until a task executes, since a task may change any file, so what follows it is checked afresh, as a second invocation would.
    """

    def __init__(
        self,
        context: Context,
        project: Project,
        records: dict[tuple[str, ...], _state.Record],
        moved: dict[tuple[str, ...], tuple[str, ...]],
        cache: HashCache,
        state_path: str,
        summary: Summary,
        progress_cb: Callable[[str], None],
    ) -> None:
        self.context = context
        self.project = project
        self.records = records
        self.moved = moved
        self.cache = cache
        self.state_path = state_path
        self.summary = summary
        self.progress_cb = progress_cb
        self.steps = {definition: step for step, definition in enumerate(project.definitions)}
        self.producers = project.graph.producers
        self.steps_by_key = {
            _state.calc_key(definition.outputs): step
            for definition, step in self.steps.items()
            if not definition.is_task
        }
        # Each rule that executed and awaits its Built, with its recipe and the inputs that moved.
        self.finishing: dict[int, tuple[Recipe, tuple[str, ...]]] = {}
        self.total = 0
        # The rules and tasks reached so far, and how many of the session's verdicts that counts.
        self.reached = 0
        self.counted = 0
        self.has_executed = False
        self.snapshot: Snapshot | None = None
        # Each output this invocation built, with its rule and the hash it left.
        self.built: dict[str, tuple[Definition, str]] = {}
        # By output, the count of executions when last found intact, so none is rechecked until another recipe runs.
        self.executions = 0
        self.intact_at: dict[str, int] = {}
        # By a path key's prefix up to its last slash, the rule outputting that directory or one holding it.
        self.holders: dict[str, Definition | None] = {}
        # The reported paths that _find_holder found no rule for.
        self.unheld: set[str] = set()
        self.engine: Engine
        # What the session's engine was told of each path, with the stamp that vouches for it.
        self.observed: dict[str, Hashed | None]
        self._open_session()

    def save_listing(self) -> None:
        """Save the tree as this invocation leaves it, so a file its recipes wrote never counts as new, even when one failed. Losing the listing costs only rebuilds."""
        if not self.has_executed:
            return
        if _state.has_added_names(self.records):
            with contextlib.suppress(OSError):
                listing = frozenset(iter_listed_files(self.context.out_dir))
                _state.save_listing(self.state_path, listing)

    def save_hashes(self) -> None:
        """Save what the hash cache learned. Losing it costs only reads, and a file new in a directory output read as new."""
        with contextlib.suppress(OSError):
            _state.save_hashes(self.state_path, self.cache.take_changes(is_final=True))

    def build(self, targets: list[Definition], task_args: tuple[str, ...] | None) -> None:
        """Build `targets` in order: each run of rules among them together, and each task once the rules before it and the rules it inputs are current."""
        sessions = self._split_sessions(targets)
        planned = [len(self.engine.find_closure(self._find_steps(session))) for session in sessions]
        self.total = sum(planned) + sum(session.task is not None for session in sessions)
        for number, session in enumerate(sessions):
            if number:
                self._open_session()
                closure = self.engine.find_closure(self._find_steps(session))
                self.total += len(closure) - planned[number]
            self._build_steps(session.rules)
            if session.task is None:
                continue
            self._build_steps(self.project.graph.upstream[self.steps[session.task]])
            self.reached += 1
            self._announce(session.task, self.reached)
            self._execute(session.task, task_args)
            self.summary.tasks_run += 1

    def validate_built_intact(self) -> None:
        """Raise RecipeFailure naming the first output this invocation built whose content changed after its rule finished, which only an undeclared write explains. One that vanished passes, since the next invocation rebuilds it."""
        damaged = [
            (output, rule)
            for output, (rule, _) in self.built.items()
            if self._find_damage(output) == _Damage.CHANGED
        ]
        if not damaged:
            return
        (output, rule), *others = damaged
        notes = tuple(
            Note(other.location, f"{other_output}, which {other.label} output, changed too")
            for other_output, other in others
        )
        reason = f"its output {output} changed after it finished"
        raise RecipeFailure(rule, reason=reason, notes=notes)

    def _split_sessions(self, targets: list[Definition]) -> list[_Session]:
        sessions = []
        rules: list[int] = []
        for target in targets:
            if target.is_task:
                sessions.append(_Session(rules, target))
                rules = []
            else:
                rules.append(self.steps[target])
        if rules:
            sessions.append(_Session(rules, None))
        return sessions

    def _find_steps(self, session: _Session) -> list[int]:
        """Return every step `session` asks its engine for."""
        if session.task is None:
            return session.rules
        return [*session.rules, *self.project.graph.upstream[self.steps[session.task]]]

    def _open_session(self) -> None:
        """Start an engine that has checked nothing, holding the trace of every record."""
        self.engine = Engine(self.project.graph)
        self.observed = {}
        self.counted = 0
        unheld = self.unheld
        for key, record in self.records.items():
            follows = [
                holder
                for path, _ in record.trace.found
                if path not in unheld and (holder := self._find_holder(path)) is not None
            ]
            self.engine.load_trace(self.steps_by_key[key], record.trace, follows)

    def _find_holder(self, path: str) -> str | None:
        """Return an output of the rule that outputs `path`, a directory holding it, or a path differing from it only in case, which a rule that read `path` must follow."""
        producer = self._find_producer(path)
        if producer is None:
            self.unheld.add(path)
            return None
        return producer.outputs[0]

    def _build_steps(self, steps: Iterable[int]) -> None:
        """Bring `steps` up to date by answering the engine's events until it has none, raising RecipeFailure on the first failure."""
        self.engine.request(steps)
        try:
            while (event := self.engine.poll()) is not Pause.DONE:
                assert not isinstance(event, Pause), "one worker never waits on another"
                try:
                    self._answer(event)
                except OSError as error:
                    rule = self.project.definitions[event.step]
                    raise RecipeFailure(rule, reason=f"{error}") from error
        finally:
            self._count_checked()

    def _count_checked(self) -> None:
        """Count the rules checked since the last count, which holds even when a failure or an interrupt ends the build."""
        checked = list(self.engine.verdicts.items())[self.counted :]
        self.counted += len(checked)
        self.reached += len(checked)
        self.summary.outputs_current += sum(
            len(self.project.definitions[step].outputs)
            for step, verdict in checked
            if verdict.reason is Reason.CURRENT
        )

    def _answer(self, event: NeedDigests | Run | Built | Failed) -> None:
        if isinstance(event, NeedDigests):
            self.engine.give_digests({path: self._observe(path) for path in event.keys})
        elif isinstance(event, Run):
            self._run(event.step)
        elif isinstance(event, Built):
            self._record(event.step, event.trace)
        else:
            raise self._build_missing_failure(event)

    def _observe(self, path: str) -> str | None:
        """Return the hash of what is at `path` for the engine: of an output stat-checked afresh, and of any other path as the session first saw it."""
        step = self.producers.get(path)
        if step is None:
            hashed = self._fetch_once(path)
            return None if hashed is None else hashed.digest
        new_files: list[str] = []
        hashed = self.observed[path] = self.cache.fetch(path, is_fresh=True, new_files=new_files)
        if new_files:
            self._forget_shadowed(new_files)
        self.intact_at[path] = self.executions
        if hashed is None:
            return None
        if step in self.finishing:
            self.built[path] = (self.project.definitions[step], hashed.digest)
        return hashed.digest

    def _fetch_once(self, path: str) -> Hashed | None:
        """Return what the session first saw at `path`, which is what the engine holds of it."""
        if path not in self.observed:
            self.observed[path] = self.cache.fetch(path)
        return self.observed[path]

    def _forget_shadowed(self, new_files: list[str]) -> None:
        """Forget at once each record a file new in a directory output shadows."""
        shadowed = _find_shadowed(self.records, new_files)
        _state.remove(self.state_path, shadowed)
        for key in shadowed:
            del self.records[key]
            self.engine.forget_trace(self.steps_by_key[key])

    def _run(self, step: int) -> None:
        """Execute the recipe of the stale rule at `step`, and tell the engine how it ended and what it reported."""
        rule = self.project.definitions[step]
        self._validate_inputs_intact(step)
        key = _state.calc_key(rule.outputs)
        record = self.records.get(key)
        before = {path: self._fetch_once(path) for path in rule.inputs}
        if record is not None:
            _state.remove(self.state_path, [key])
            before.update((path, self._fetch_once(path)) for path, _ in record.trace.found)
        for output in rule.outputs:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        self._announce(rule, self.reached + len(self.engine.verdicts) - self.counted)
        if self.snapshot is None:
            self.snapshot = Snapshot(self.cache, self.context.out_dir)
        recipe = self._execute(rule, None)
        reported = sorted(recipe.reported)
        for path in reported:
            self._validate_ordered(step, path)
        moved = self._find_moved_inputs(recipe, before)
        self.finishing[step] = (recipe, moved)
        self.engine.finish(step, Status.UNSETTLED if moved else Status.OK, reported)

    def _record(self, step: int, trace: Trace | None) -> None:
        """Save the `trace` of the rule at `step`, which executed and wrote every output, or where it has none, the inputs that moved."""
        rule = self.project.definitions[step]
        recipe, moved = self.finishing.pop(step)
        self.summary.rules_run += 1
        key = _state.calc_key(rule.outputs)
        if trace is None:
            self._leave_unrecorded(rule, key, moved)
            return
        record = self.records[key] = _state.Record(trace, tuple(sorted(recipe.reported_names)))
        _state.save(self.state_path, key, record, self.cache.take_changes())
        self.moved.pop(key, None)

    def _build_missing_failure(self, event: Failed) -> RecipeFailure:
        rule = self.project.definitions[event.step]
        if event.missing is Missing.INPUT:
            return RecipeFailure(rule, reason=f"its input {event.key} is missing")
        if event.missing is Missing.FOUND:
            reason = f"its recipe reported reading {event.key}, which it then removed"
            return RecipeFailure(rule, reason=reason)
        missing = [
            output for output in _state.calc_key(rule.outputs) if self.observed[output] is None
        ]
        reason = f"its recipe succeeded without writing {', '.join(missing)}"
        return RecipeFailure(rule, reason=reason)

    def _validate_inputs_intact(self, step: int) -> None:
        """Fail the rule at `step` without executing it where an output this invocation built, which it inputs or orders after, changed or vanished since its rule finished."""
        graph = self.project.graph
        for output in (*graph.steps[step].inputs, *graph.steps[step].order_only):
            if output not in graph.producers:
                continue
            damage = self._find_damage(output)
            if damage is not None:
                producer = self.project.definitions[graph.producers[output]]
                raise RecipeFailure(
                    self.project.definitions[step],
                    reason=f"its input {output} {damage} after {producer.label} finished",
                    notes=(Note(producer.location, f"{producer.label} outputs {output}"),),
                )

    def _find_damage(self, output: str) -> _Damage | None:
        """Return how the output `output` this invocation built differs from how its rule left it, or None where it doesn't, or where no recipe executed since it was last found intact."""
        built = self.built.get(output)
        if built is None or self.intact_at.get(output) == self.executions:
            return None
        current = self.cache.fetch(output, is_fresh=True)
        if current is None:
            return _Damage.VANISHED
        if current.digest != built[1]:
            return _Damage.CHANGED
        self.intact_at[output] = self.executions
        self.observed[output] = current
        return None

    def _find_moved_inputs(
        self, recipe: Recipe, before: dict[str, Hashed | None]
    ) -> tuple[str, ...]:
        """Return the inputs that changed while the recipe executed, even where the content changed back, so recording the rule would claim it current for files its tool never read.

        `before` holds what the engine was told of each declared input and each found input in the rule's record. A file first reported has none, since its tool read it before the recipe could report it, so it compares with the snapshot, or where a rule outputs it, with how this invocation last found it, unless the recipe wrote it in Python itself.
        """
        moved = {
            path
            for path, hashed in before.items()
            if self.cache.fetch(path, is_fresh=True) != hashed
        }
        assert self.snapshot is not None
        for path in recipe.reported - before.keys():
            if calc_path_key(path) in recipe.written:
                continue
            if self._find_producer(path) is not None:
                has_moved = self.cache.has_moved_since_fetched(path)
            else:
                has_moved = self.snapshot.has_moved(path)
            if has_moved:
                moved.add(path)
        return tuple(sorted(moved))

    def _leave_unrecorded(
        self, rule: Definition, key: tuple[str, ...], moved: tuple[str, ...]
    ) -> None:
        """Leave `rule` stale, keeping the inputs that `moved`, and warn where one of them also changed during the rule's last execution, since a rule whose own tool changes its input never settles."""
        self.records.pop(key, None)
        repeated = [path for path in moved if path in self.moved.get(key, ())]
        if repeated:
            message = f"{rule.label} stays stale: {repeated[0]} changed while its recipe executed, in this execution and its last"
            self.summary.unsettled.append(Diagnostic(rule.location, message))
        self.moved[key] = moved
        _state.save_moved(self.state_path, key, moved, self.cache.take_changes())

    def _validate_ordered(self, step: int, path: str) -> None:
        """Fail the rule at `step`, whose recipe reported reading `path`, unless it declares an input that orders it after the rule outputting `path`."""
        rule = self.project.definitions[step]
        producer = self._find_producer(path)
        if producer is None or producer is rule:
            return
        if self.steps[producer] in self.project.graph.upstream[step]:
            return
        raise RecipeFailure(
            rule,
            reason=f"its recipe reported reading {path}, though no fac.Input or fac.OrderOnly parameter orders it after the rule that outputs it",
            notes=(Note(producer.location, f"{producer.label} outputs {path}"),),
        )

    def _find_producer(self, path: str) -> Definition | None:
        """Return the rule that outputs `path`, or a directory holding it."""
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
        self.progress_cb(f"[{position}/{self.total}] {definition.label}")

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
            thread_id=threading.get_ident(),
            tracked=frozenset(map(calc_path_key, (*definition.inputs, *definition.outputs))),
            order_only=frozenset(map(calc_path_key, definition.order_only)),
            exempt=frozenset(data_paths),
            shared_modules=self.project.shared_modules,
            output_keys=self.project.producers_by_key.keys(),
        )

    def _execute(self, definition: Definition, task_args: tuple[str, ...] | None) -> Recipe:
        args, kwargs = definition.calc_call(task_args)
        recipe = self._build_recipe(definition)
        self.context.running = recipe
        self.has_executed = True
        self.executions += 1
        try:
            definition.fn(*args, **kwargs)
        except KeyboardInterrupt:
            self.summary.stopped = definition.label
            raise
        except BaseException as error:
            if recipe.undeclared is None:
                raise RecipeFailure(definition, error=error) from error
        finally:
            self.context.running = None
        if recipe.undeclared is not None:
            path, reason = recipe.undeclared
            producer = self._find_producer(path)
            notes = (
                (Note(producer.location, f"{producer.label} outputs {path}"),) if producer else ()
            )
            raise RecipeFailure(definition, reason=reason, notes=notes)
        return recipe
