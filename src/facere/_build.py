"""Building targets: deciding which rules are stale, and executing recipes one at a time in dependency order."""

import hashlib
import os
import posixpath
import shlex
import subprocess
import sys
import traceback
from dataclasses import dataclass

from facere import _state
from facere._collect import Definition, Project
from facere._command import write_output
from facere._context import Context, Running, normalize
from facere._diagnostics import Diagnostic, FacereError, Note, print_error
from facere._hash import feed, hash_path


class RecipeFailure(Exception):
    def __init__(
        self, definition: Definition, *, error: BaseException | None = None, reason: str = ""
    ) -> None:
        super().__init__(definition.label)
        self.definition = definition
        self.error = error
        self.reason = reason


@dataclass(slots=True)
class Summary:
    executed: int = 0
    up_to_date: int = 0


def resolve_targets(project: Project, root: str, targets: list[str]) -> list[Definition]:
    """Return the definitions `targets` resolve to, in order, or the defaults when `targets` is empty."""
    names_note = Note(None, f"names: {', '.join(sorted(project.by_name))}")
    if not targets:
        defaults = [definition for definition in project.definitions if definition.is_default]
        if not defaults:
            raise FacereError(
                Diagnostic(
                    None,
                    "fac.py declares no default, so name a target, or pass default=True to fac.rule or fac.task",
                    (names_note,),
                )
            )
        return defaults
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
        raise FacereError(
            Diagnostic(
                None,
                f"unknown target {listed}: name a rule or task, or give the path a rule outputs, relative to the root",
                (names_note,),
            )
        )
    return resolved


def build(context: Context, project: Project, targets: list[Definition]) -> Summary:
    """Build `targets` in order, raising RecipeFailure on the first failure."""
    state_path = posixpath.join(context.state_dir, "state.db")
    records = _state.load(state_path)
    declared = {
        _state.calc_key(definition.outputs)
        for definition in project.definitions
        if not definition.is_task
    }
    _state.remove(state_path, [key for key in records if key not in declared])
    builder = _Builder(context, project, records, state_path)
    for target in targets:
        builder.build(target)
    return builder.summary


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
    print_error(FacereError(Diagnostic(failure.definition.location, message)), start_dir)


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


class _Builder:
    def __init__(
        self,
        context: Context,
        project: Project,
        records: dict[tuple[str, ...], _state.Record],
        state_path: str,
    ) -> None:
        self.context = context
        self.project = project
        self.records = records
        self.state_path = state_path
        self.checked: set[Definition] = set()
        self.summary = Summary()

    def build(self, target: Definition) -> None:
        for rule in self._order(target):
            try:
                self._ensure_up_to_date(rule)
            except OSError as error:
                raise RecipeFailure(
                    rule, reason=f"{error}: fix the path or its permissions"
                ) from error
        if target.is_task:
            self._execute(target)
            self.summary.executed += 1
            self.checked.clear()

    def _order(self, target: Definition) -> list[Definition]:
        """Return the rules `target` needs that this batch hasn't checked, each after the rules that output its inputs."""
        if target in self.checked:
            return []
        order = []
        seen = {*self.checked, target}
        stack = [(target, iter(target.inputs))]
        while stack:
            definition, inputs = stack[-1]
            path = next(inputs, None)
            if path is None:
                stack.pop()
                if not definition.is_task:
                    order.append(definition)
                continue
            rule = self.project.producers.get(path)
            if rule is not None and rule not in seen:
                seen.add(rule)
                stack.append((rule, iter(rule.inputs)))
        return order

    def _ensure_up_to_date(self, rule: Definition) -> None:
        self.checked.add(rule)
        fingerprint = self._calc_fingerprint(rule)
        key = _state.calc_key(rule.outputs)
        record = self.records.get(key)
        if record is not None:
            if record == (fingerprint, tuple(hash_path(output) for output in key)):
                self.summary.up_to_date += 1
                return
            _state.remove(self.state_path, [key])
        for output in rule.outputs:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        self._execute(rule)
        output_hashes = {output: hash_path(output) for output in key}
        missing = [output for output, content in output_hashes.items() if content is None]
        if missing:
            raise RecipeFailure(
                rule,
                reason=f"its recipe succeeded without writing {', '.join(missing)}: write every declared output, or fix the path",
            )
        record = self.records[key] = _state.Record(
            fingerprint, tuple(content for content in output_hashes.values() if content is not None)
        )
        _state.save(self.state_path, key, record)
        self.summary.executed += 1

    def _calc_fingerprint(self, rule: Definition) -> str:
        digest = hashlib.sha256(self.project.code_digests[rule])
        for path in rule.inputs:
            content = hash_path(path)
            if content is None:
                raise RecipeFailure(
                    rule,
                    reason=f"its input {path} is missing: restore it, or fix the rule that outputs it",
                )
            feed(digest, b"path", path.encode("utf-8", "surrogateescape"))
            feed(digest, b"content", content.encode())
        return digest.hexdigest()

    def _execute(self, definition: Definition) -> None:
        self.context.running = Running.TASK if definition.is_task else Running.RULE
        try:
            definition.fn(*definition.args, **definition.kwargs)
        except KeyboardInterrupt:
            raise
        except BaseException as error:
            raise RecipeFailure(definition, error=error) from error
        finally:
            self.context.running = None
