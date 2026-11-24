#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click"]
# ///
"""Inject one staleness bug at a time into Facere's source and report whether the oracle in test/oracle/ notices.

Each mutant swaps one exact string in `src/facere/` for a broken one, runs the oracle's state machine without shrinking, and restores the file. A mutant whose string no longer occurs exactly once reports UNMATCHED, so update it to the code as it now reads.
"""

import os
import subprocess
import sys
from pathlib import Path

import click

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "src" / "facere"
SCRATCH_TEST = REPO / "test" / "oracle" / "test_mutants_scratch.py"
DEFAULT_BASETEMP = REPO / "build" / "oracle-mutants"
SCRATCH_TEST_TEXT = """\
import os
from pathlib import Path

import pytest
from hypothesis import Phase, settings

from .test_oracle import _SETTINGS, _run_machine


def test_mutant_is_caught(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    examples = int(os.environ["ORACLE_MUTANT_EXAMPLES"])
    quick = settings(_SETTINGS, max_examples=examples, stateful_step_count=15, phases=[Phase.generate])
    _run_machine(tmp_path / "example", capfd, quick, fixed_seed=1)
"""
MUTANTS = {
    "bool-hashes-as-int": (
        "_hash.py",
        'feed(digest, b"B", b"1" if value else b"0")',
        'feed(digest, b"I", int(value).to_bytes(1, "little", signed=True))',
    ),
    "values-unhashed": (
        "_collect.py",
        '            ("parameter", definition.values, output_keys),\n',
        "",
    ),
    "globals-unhashed": (
        "_hash.py",
        "        return (name, namespace[name]) if name in namespace else None",
        "        return None",
    ),
    "module-attributes-unfollowed": (
        "_collect.py",
        "        return _is_project_code(context, module)",
        "        return False",
    ),
    "docstrings-kept": (
        "_hash.py",
        "        if ast.get_docstring(inner, clean=False) is not None:",
        "        if False:",
    ),
    "env-unhashed": ("_collect.py", '        feed(digest, b"env", env)\n', ""),
    "epoch-unhashed": (
        "_collect.py",
        '        feed(digest, b"epoch", str(context.epoch).encode())\n',
        "",
    ),
    "paths-unhashed": (
        "_collect.py",
        '            ("path parameter", definition.path_values, None),\n',
        "",
    ),
    "input-content-unhashed": (
        "_engine.py",
        "    if trace.inputs != tuple((key, digests[key]) for key in inputs):",
        "    if False:",
    ),
    "executable-bit-ignored": (
        "_cache.py",
        'is_executable = sys.platform != "win32" and bool(mode & stat.S_IXUSR)',
        "is_executable = False",
    ),
    "outputs-unverified": (
        "_engine.py",
        "        if digests[key] != recorded.get(key):",
        "        if False:",
    ),
    "added-inputs-unchecked": (
        "_engine.py",
        "        if current == digest:",
        "        if current == digest or current is not _UNKNOWN:",
    ),
    "shadowing-off": (
        "_build.py",
        "    if not _state.has_added_names(records):\n        return records",
        "    if True:\n        return records",
    ),
    "order-only-paths-unhashed": (
        "_collect.py",
        "            value = path_values[parameter] = paths if slot.is_list else paths[0]",
        "            value = paths if slot.is_list else paths[0]\n"
        "            if slot.kind is not Kind.ORDER_ONLY:\n"
        "                path_values[parameter] = value",
    ),
    "failed-record-kept": (
        "_build.py",
        "            self._remove_saved([_state.calc_key(rule.outputs)])",
        "            pass",
    ),
    "keep-going-stops": (
        "_engine.py",
        "        if not self._keep_going:\n            self._has_stopped = True",
        "        if True:\n            self._has_stopped = True",
    ),
    "downstream-of-failure-executes": (
        "_engine.py",
        "                if state in _FAILED_STATES:\n                    self._doomed.add(dependent)",
        "                if False:\n                    self._doomed.add(dependent)",
    ),
    "ctime-unstamped": (
        "_cache.py",
        "    return _format_stamp(info, change_ns), max(info.st_mtime_ns, change_ns)",
        "    return _format_stamp(info, 0), max(info.st_mtime_ns, change_ns)",
    ),
    "stamps-unchecked": (
        "_cache.py",
        "            and entry.stamp == stamp\n",
        "",
    ),
    "bytecode-trusted": (
        "_bytecode.py",
        "    cached_root = os.path.dirname(",
        "    return\n    cached_root = os.path.dirname(",
    ),
}


def _run_oracle(examples: int, basetemp: Path) -> subprocess.CompletedProcess[str]:
    command = ["uv", "run", "--locked", "--directory", str(REPO), "pytest", str(SCRATCH_TEST)]
    command += ["-n0", "-q", "-x", f"--basetemp={basetemp}"]
    env = {**os.environ, "ORACLE_MUTANT_EXAMPLES": str(examples)}
    return subprocess.run(command, capture_output=True, text=True, env=env, check=False)


def _check_mutant(name: str, examples: int, basetemp: Path) -> str:
    """Return CAUGHT, MISSED, or UNMATCHED for the mutant `name`, with the oracle's first failure line when caught."""
    file, old, new = MUTANTS[name]
    path = SOURCE / file
    original = path.read_text(encoding="utf-8")
    if original.count(old) != 1:
        return "UNMATCHED"
    path.write_text(original.replace(old, new), encoding="utf-8")
    try:
        result = _run_oracle(examples, basetemp)
    finally:
        path.write_text(original, encoding="utf-8")
    if result.returncode == 0:
        return "MISSED"
    failure = next((line for line in result.stdout.splitlines() if "Error" in line), "")
    return f"CAUGHT {failure.removeprefix('E').strip()[:200]}"


@click.command()
@click.argument("names", nargs=-1, type=click.Choice(sorted(MUTANTS)))
@click.option(
    "--examples", default=60, show_default=True, help="Examples the oracle runs per mutant."
)
@click.option(
    "--basetemp",
    type=click.Path(path_type=Path),
    default=DEFAULT_BASETEMP,
    show_default=True,
    help="Where the oracle builds its projects. A directory on tmpfs runs several times faster.",
)
def main(names: tuple[str, ...], examples: int, basetemp: Path) -> None:
    """Check that the oracle catches each mutant in NAMES, or every mutant when none is named."""
    SCRATCH_TEST.write_text(SCRATCH_TEST_TEXT, encoding="utf-8")
    try:
        results = {}
        for name in names or MUTANTS:
            results[name] = _check_mutant(name, examples, basetemp)
            click.echo(f"{name}: {results[name]}")
    finally:
        SCRATCH_TEST.unlink()
    if not all(result.startswith("CAUGHT") for result in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
