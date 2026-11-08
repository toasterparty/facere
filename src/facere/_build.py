"""Building targets: deciding which rules are stale, and executing recipes one at a time in dependency order."""

import contextlib
import hashlib
import os
import posixpath
import shlex
import subprocess
import sys
import threading
import traceback
from collections.abc import Callable

from facere import _state
from facere._collect import Definition, Project
from facere._command import write_output
from facere._context import (
    Context,
    Recipe,
    calc_path_key,
    is_within,
    iter_self_and_parents,
    normalize,
)
from facere._diagnostics import Diagnostic, FacereError, Note, print_error
from facere._hash import feed, hash_path, iter_strings
from facere._summary import Summary
from facere._undeclared import ensure_audit_hook


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
    state_path = posixpath.join(context.state_dir, "state.db")
    records = _state.load(state_path)
    declared = {
        _state.calc_key(definition.outputs)
        for definition in project.definitions
        if not definition.is_task
    }
    try:
        _state.remove(state_path, [key for key in records if key not in declared])
        records = _remove_shadowed(context, state_path, records)
    except OSError as error:
        raise FacereError(Diagnostic(None, f"{error}")) from error
    ensure_audit_hook()
    total = _calc_total(project.producers, targets)
    builder = _Builder(context, project, records, state_path, summary, progress_cb, total)
    try:
        for target in targets:
            builder.build(target, task_args)
    finally:
        builder.save_listing()


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


def _list_files(out_dir: str) -> frozenset[str]:
    """Return every file under the working directory, as normalize returns them, outside `out_dir` and any hidden directory."""
    files = set()
    for directory, subdirectories, names in os.walk("."):
        relative = posixpath.normpath(directory.replace(os.sep, "/"))
        subdirectories[:] = [
            name
            for name in subdirectories
            if not name.startswith(".")
            and not is_within(posixpath.normpath(posixpath.join(relative, name)), out_dir)
        ]
        files.update(posixpath.normpath(posixpath.join(relative, name)) for name in names)
    return frozenset(files)


def _remove_shadowed(
    context: Context, state_path: str, records: dict[tuple[str, ...], _state.Record]
) -> dict[tuple[str, ...], _state.Record]:
    """Forget each record that names a file name a file new since the last invocation has, whether or not this invocation's targets reach its rule, and return the records left."""
    if not _has_added_names(records):
        return records
    listing = _list_files(context.out_dir)
    saved = _state.load_listing(state_path)
    if listing == saved:
        return records
    new_names = {calc_path_key(posixpath.basename(path)) for path in listing - saved}
    shadowed = {
        key for key, record in records.items() if not new_names.isdisjoint(record.added_names)
    }
    _state.remove(state_path, list(shadowed))
    _state.save_listing(state_path, listing)
    return {key: record for key, record in records.items() if key not in shadowed}


def _has_added_names(records: dict[tuple[str, ...], _state.Record]) -> bool:
    """Say whether any record holds a file name a new file could shadow, which alone makes the tree's listing worth keeping."""
    return any(record.added_names for record in records.values())


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


def _calc_total(producers: dict[str, Definition], targets: list[Definition]) -> int:
    """Return the rules and tasks building `targets` reaches, as _Builder.build counts them."""
    checked: set[Definition] = set()
    total = 0
    for target in targets:
        order = _order(producers, target, checked)
        total += len(order) + target.is_task
        checked.update(order)
        if target.is_task:
            checked.clear()
    return total


def _order(
    producers: dict[str, Definition], target: Definition, checked: set[Definition]
) -> list[Definition]:
    """Return the rules `target` needs that aren't in `checked`, each after the rules that output its inputs."""
    if target in checked:
        return []
    order = []
    seen = {*checked, target}
    stack = [(target, iter(target.prerequisites))]
    while stack:
        definition, inputs = stack[-1]
        path = next(inputs, None)
        if path is None:
            stack.pop()
            if not definition.is_task:
                order.append(definition)
            continue
        rule = producers.get(path)
        if rule is not None and rule not in seen:
            seen.add(rule)
            stack.append((rule, iter(rule.prerequisites)))
    return order


class _Builder:
    def __init__(
        self,
        context: Context,
        project: Project,
        records: dict[tuple[str, ...], _state.Record],
        state_path: str,
        summary: Summary,
        progress_cb: Callable[[str], None],
        total: int,
    ) -> None:
        self.context = context
        self.project = project
        self.records = records
        self.state_path = state_path
        self.checked: set[Definition] = set()
        self.summary = summary
        self.progress_cb = progress_cb
        self.total = total
        self.position = 0
        self.has_executed = False

    def save_listing(self) -> None:
        """Save the tree as this invocation leaves it, so a file its recipes wrote never counts as new, even when one failed. Losing the listing costs only rebuilds."""
        if not self.has_executed:
            return
        if _has_added_names(self.records):
            with contextlib.suppress(OSError):
                _state.save_listing(self.state_path, _list_files(self.context.out_dir))

    def build(self, target: Definition, task_args: tuple[str, ...] | None) -> None:
        for rule in _order(self.project.producers, target, self.checked):
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

    def _ensure_up_to_date(self, rule: Definition) -> None:
        self.checked.add(rule)
        self.position += 1
        fingerprint = self._calc_fingerprint(rule)
        key = _state.calc_key(rule.outputs)
        record = self.records.get(key)
        hashes_before: dict[str, str | None] = {}
        if record is not None:
            hashes_before = {path: hash_path(path) for path, _ in record.added_inputs}
            if (
                record.fingerprint == fingerprint
                and record.output_hashes == tuple(hash_path(output) for output in key)
                and all(hashes_before[path] == content for path, content in record.added_inputs)
            ):
                self.summary.outputs_current += len(key)
                return
            _state.remove(self.state_path, [key])
        for output in rule.outputs:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        self._announce(rule)
        recipe = self._execute(rule, None)
        added_inputs = self._hash_added_inputs(rule, recipe, hashes_before)
        output_hashes = {output: hash_path(output) for output in key}
        missing = [output for output, content in output_hashes.items() if content is None]
        if missing:
            raise RecipeFailure(
                rule,
                reason=f"its recipe succeeded without writing {', '.join(missing)}",
            )
        record = self.records[key] = _state.Record(
            fingerprint,
            tuple(content for content in output_hashes.values() if content is not None),
            added_inputs,
            tuple(sorted(recipe.reported_names)),
        )
        _state.save(self.state_path, key, record)
        self.summary.rules_run += 1

    def _hash_added_inputs(
        self, rule: Definition, recipe: Recipe, hashes_before: dict[str, str | None]
    ) -> tuple[tuple[str, str], ...]:
        """Return what `rule`'s recipe reported, each path with its hash from before the recipe where one exists, so a change during the recipe makes the rule stale."""
        added = []
        for path in sorted(recipe.reported.values()):
            self._validate_ordered(rule, path)
            content = hashes_before.get(path) or hash_path(path)
            if content is None:
                reason = f"its recipe reported reading {path}, which it then removed"
                raise RecipeFailure(rule, reason=reason)
            added.append((path, content))
        return tuple(added)

    def _validate_ordered(self, rule: Definition, path: str) -> None:
        producer = self._find_producer(path)
        if producer is None or producer is rule:
            return
        if any(output in rule.prerequisites for output in producer.outputs):
            return
        raise RecipeFailure(
            rule,
            reason=f"its recipe reported reading {path}, though no fac.Input or fac.OrderOnly parameter orders it after the rule that outputs it",
            notes=(Note(producer.location, f"{producer.label} outputs {path}"),),
        )

    def _find_producer(self, path: str) -> Definition | None:
        """Return the rule that outputs `path`, or a directory holding it."""
        for ancestor in iter_self_and_parents(calc_path_key(path)):
            producer = self.project.producers_by_key.get(ancestor)
            if producer is not None:
                return producer
        return None

    def _calc_fingerprint(self, rule: Definition) -> str:
        digest = hashlib.sha256(self.project.code_digests[rule])
        for path in rule.inputs:
            content = hash_path(path)
            if content is None:
                raise RecipeFailure(
                    rule,
                    reason=f"its input {path} is missing",
                )
            feed(digest, b"path", path.encode("utf-8", "surrogateescape"))
            feed(digest, b"content", content.encode())
        return digest.hexdigest()

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
