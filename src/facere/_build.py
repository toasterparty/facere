"""Building targets: deciding which rules are stale, and executing recipes one at a time in dependency order."""

import contextlib
import enum
import hashlib
import os
import posixpath
import shlex
import subprocess
import sys
import threading
import traceback
from collections.abc import Callable, Iterable

from facere import _state
from facere._cache import HashCache, Hashed, Snapshot, iter_listed_files
from facere._collect import Definition, Project, iter_upstream
from facere._command import write_output
from facere._context import (
    STATE_FILE_NAME,
    Context,
    Recipe,
    calc_path_key,
    is_within,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note, print_error
from facere._hash import feed, iter_strings
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
            rule = project.producers.get(normalize(target.replace("\\", "/"), root))
            found = [rule] if rule else []
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
    total, planned = _plan(project.upstream, targets)
    builder = _Builder(
        context,
        project,
        records,
        state.moved,
        HashCache(state.hashes),
        state_path,
        summary,
        progress_cb,
        total,
        planned,
    )
    try:
        for target in targets:
            builder.build(target, task_args)
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
    new_paths = (listing - saved_listing) | new_outputs
    records = _forget_shadowed(state_path, records, new_paths)
    if listing != saved_listing:
        _state.save_listing(state_path, listing)
    return records


def _forget_shadowed(
    state_path: str, records: dict[tuple[str, ...], _state.Record], new_paths: Iterable[str]
) -> dict[tuple[str, ...], _state.Record]:
    """Forget each record naming the file name of one of `new_paths`, and return the records left."""
    new_names = {calc_path_key(posixpath.basename(path)) for path in new_paths}
    shadowed = [
        key for key, record in records.items() if not new_names.isdisjoint(record.added_names)
    ]
    _state.remove(state_path, shadowed)
    return {key: record for key, record in records.items() if key not in shadowed}


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


def _plan(
    upstream: dict[str, tuple[Definition, ...]], targets: list[Definition]
) -> tuple[int, set[Definition]]:
    """Return how many rules and tasks building `targets` reaches, as _Builder.build counts them, and the rules among them."""
    checked: set[Definition] = set()
    planned: set[Definition] = set()
    total = 0
    for target in targets:
        order = _order(upstream, target, checked)
        total += len(order) + target.is_task
        checked.update(order)
        planned.update(order)
        if target.is_task:
            checked.clear()
    return total, planned


def _order(
    upstream: dict[str, tuple[Definition, ...]], target: Definition, checked: set[Definition]
) -> list[Definition]:
    """Return the rules `target` needs that aren't in `checked`, each after the rules that output its inputs or paths inside them."""
    if target in checked:
        return []
    order = []
    seen = {*checked, target}
    stack = [(target, iter_upstream(target, upstream))]
    while stack:
        definition, edges = stack[-1]
        _, rule = next(edges, (None, None))
        if rule is None:
            stack.pop()
            if not definition.is_task:
                order.append(definition)
            continue
        if rule not in seen:
            seen.add(rule)
            stack.append((rule, iter_upstream(rule, upstream)))
    return order


class _Builder:
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
        total: int,
        planned: set[Definition],
    ) -> None:
        self.context = context
        self.project = project
        self.records = records
        self.moved = moved
        self.cache = cache
        self.state_path = state_path
        self.checked: set[Definition] = set()
        self.summary = summary
        self.progress_cb = progress_cb
        self.total = total
        self.planned = planned
        self.position = 0
        self.has_executed = False
        self.snapshot: Snapshot | None = None
        # Each output this invocation built, with its rule and the hash it left.
        self.built: dict[str, tuple[Definition, str]] = {}
        # By output, the count of executions when last found intact, so none is rechecked until another recipe runs.
        self.executions = 0
        self.intact_at: dict[str, int] = {}
        self.producers_by_path: dict[str, Definition | None] = {}

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

    def build(self, target: Definition, task_args: tuple[str, ...] | None) -> None:
        for rule in _order(self.project.upstream, target, self.checked):
            try:
                self._ensure_up_to_date(rule)
            except OSError as error:
                raise RecipeFailure(rule, reason=f"{error}") from error
        if target.is_task:
            self.position += 1
            self._announce(target)
            self._execute(target, task_args)
            self.summary.tasks_run += 1
            self.checked.clear()

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

    def _ensure_up_to_date(self, rule: Definition) -> None:
        self.checked.add(rule)
        self.position += 1
        self._validate_inputs_intact(rule)
        fingerprint, before = self._calc_fingerprint(rule)
        key = _state.calc_key(rule.outputs)
        record = self.records.get(key)
        if record is not None:
            self._ensure_recorded_reports_built(rule, record)
            added = {path: self.cache.fetch(path) for path, _ in record.added_inputs}
            before.update(added)
            if (
                not rule.is_always
                and record.fingerprint == fingerprint
                and record.output_hashes == self._fetch_output_hashes(key)
                and all(_digest(added[path]) == content for path, content in record.added_inputs)
            ):
                self.summary.outputs_current += len(key)
                return
            _state.remove(self.state_path, [key])
        for output in rule.outputs:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        self._announce(rule)
        if self.snapshot is None:
            self.snapshot = Snapshot(self.cache, self.context.out_dir)
        recipe = self._execute(rule, None)
        added_inputs = self._hash_added_inputs(rule, recipe, before)
        output_hashes = self._fetch_output_hashes(key)
        missing = [
            output for output, content in zip(key, output_hashes, strict=True) if not content
        ]
        if missing:
            raise RecipeFailure(
                rule,
                reason=f"its recipe succeeded without writing {', '.join(missing)}",
            )
        for output, content in zip(key, output_hashes, strict=True):
            self.built[output] = (rule, content)
        self.summary.rules_run += 1
        moved = self._find_moved_inputs(recipe, before)
        if moved:
            self._leave_unrecorded(rule, key, moved)
            return
        record = self.records[key] = _state.Record(
            fingerprint, output_hashes, added_inputs, tuple(sorted(recipe.reported_names))
        )
        _state.save(self.state_path, key, record, self.cache.take_changes())
        self.moved.pop(key, None)

    def _fetch_output_hashes(self, key: tuple[str, ...]) -> tuple[str, ...]:
        """Return the hash of each output in `key`, or an empty string for one missing, stat-checked afresh, and forget at once each record a file new in a directory output shadows."""
        new_files: list[str] = []
        hashes = tuple(
            _digest(self.cache.fetch(output, is_fresh=True, new_files=new_files)) for output in key
        )
        if new_files:
            self.records = _forget_shadowed(self.state_path, self.records, new_files)
        for output in key:
            self.intact_at[output] = self.executions
        return hashes

    def _validate_inputs_intact(self, rule: Definition) -> None:
        """Fail `rule` without executing it where an output this invocation built, which it inputs or orders after, changed or vanished since its rule finished."""
        for path, producer in iter_upstream(rule, self.project.upstream):
            for output in producer.outputs:
                if not _is_related(output, path):
                    continue
                damage = self._find_damage(output)
                if damage is not None:
                    raise RecipeFailure(
                        rule,
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
        return None

    def _find_moved_inputs(
        self, recipe: Recipe, before: dict[str, Hashed | None]
    ) -> tuple[str, ...]:
        """Return the inputs that changed while the recipe executed, even where the content changed back, so recording the rule would claim it current for files its tool never read.

        `before` holds what the rule's fingerprint and record checked of each declared input and each added input in the rule's record. A file first reported has none, since its tool read it before the recipe could report it, so it compares with the snapshot, or where a rule outputs it, with how this invocation last found it, unless the recipe wrote it in Python itself.
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

    def _ensure_recorded_reports_built(self, rule: Definition, record: _state.Record) -> None:
        """Bring up to date first each rule that now outputs a file `rule` last reported, as when a source became generated, so its record is checked against the file that rule writes."""
        for path, _ in record.added_inputs:
            producer = self._find_producer(path)
            if producer is None or producer is rule:
                continue
            for upstream_rule in _order(self.project.upstream, producer, self.checked):
                if upstream_rule not in self.planned:
                    self.planned.add(upstream_rule)
                    self.total += 1
                self._ensure_up_to_date(upstream_rule)

    def _hash_added_inputs(
        self, rule: Definition, recipe: Recipe, before: dict[str, Hashed | None]
    ) -> tuple[tuple[str, str], ...]:
        """Return what `rule`'s recipe reported, each path with its hash from before the recipe where one exists, so a change during the recipe makes the rule stale."""
        added = []
        for path in sorted(recipe.reported):
            self._validate_ordered(rule, path)
            content = _digest(before.get(path) or self.cache.fetch(path))
            if not content:
                reason = f"its recipe reported reading {path}, which it then removed"
                raise RecipeFailure(rule, reason=reason)
            added.append((path, content))
        return tuple(added)

    def _validate_ordered(self, rule: Definition, path: str) -> None:
        producer = self._find_producer(path)
        if producer is None or producer is rule:
            return
        if any(producer in self.project.upstream[input_] for input_ in rule.prerequisites):
            return
        raise RecipeFailure(
            rule,
            reason=f"its recipe reported reading {path}, though no fac.Input or fac.OrderOnly parameter orders it after the rule that outputs it",
            notes=(Note(producer.location, f"{producer.label} outputs {path}"),),
        )

    def _find_producer(self, path: str) -> Definition | None:
        """Return the rule that outputs `path`, or a directory holding it."""
        if path not in self.producers_by_path:
            self.producers_by_path[path] = next(
                (
                    self.project.producers_by_key[ancestor]
                    for ancestor in iter_self_and_parents(calc_path_key(path))
                    if ancestor in self.project.producers_by_key
                ),
                None,
            )
        return self.producers_by_path[path]

    def _calc_fingerprint(self, rule: Definition) -> tuple[str, dict[str, Hashed | None]]:
        """Return the fingerprint of `rule`, and what it hashed of each input."""
        digest = hashlib.sha256(self.project.code_digests[rule])
        hashed_inputs: dict[str, Hashed | None] = {}
        for path in rule.inputs:
            hashed = hashed_inputs[path] = self.cache.fetch(path)
            if hashed is None:
                raise RecipeFailure(
                    rule,
                    reason=f"its input {path} is missing",
                )
            feed(digest, b"path", path.encode("utf-8", "surrogateescape"))
            feed(digest, b"content", hashed.digest.encode())
        return digest.hexdigest(), hashed_inputs

    def _announce(self, definition: Definition) -> None:
        self.progress_cb(f"[{self.position}/{self.total}] {definition.label}")

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


def _digest(hashed: Hashed | None) -> str:
    """Return the hash in `hashed`, or an empty string, which no hash is, where nothing was there."""
    return "" if hashed is None else hashed.digest


def _is_related(output: str, path: str) -> bool:
    """Say whether reading `path` reads some of `output`: they are one path, or one holds the other."""
    output_key = calc_path_key(output)
    path_key = calc_path_key(path)
    return is_within(path_key, output_key) or is_within(output_key, path_key)
