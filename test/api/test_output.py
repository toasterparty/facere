"""Facere's own streams, which a rule's live command holds while other output waits."""

import io
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from facere._output import Output

from ..helpers import Fac, run_fac


def test_output_written_while_the_terminal_is_held_waits_until_after_it() -> None:
    stdout, stderr = io.StringIO(), io.StringIO()
    statuses: list[str] = []
    output = Output(stdout, stderr, statuses.append)

    with output.hold_terminal([(True, "before\n")], [(True, "after\n")]):
        output.write([(False, "other rule\n"), (True, "other error\n")])
        output.show_status("[2/3] other")
        assert (stdout.getvalue(), stderr.getvalue()) == ("", "before\n")

    assert stdout.getvalue() == "other rule\n"
    assert stderr.getvalue() == "before\nafter\nother error\n"
    assert statuses == []


@pytest.mark.project("recipe_bytes")
def test_bytes_a_rules_recipe_writes_to_stdout_buffer_stay_in_order_with_its_text(
    fac: Fac,
) -> None:
    result = fac("page")

    assert result.status == 0, result.err
    assert result.out == "before\ncaf\u00e9\nafter\n"


@pytest.mark.project("recipe_bytes")
def test_bytes_a_task_writes_to_stdout_buffer_reach_facere_stdout(fac: Fac) -> None:
    result = fac("show")

    assert result.status == 0, result.err
    assert result.out == "before\ncaf\u00e9\nafter\n"


@pytest.mark.project("breakpoint")
def test_breakpoint_in_a_rule_holds_the_terminal_until_its_recipe_ends(root: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "facere", "-j", "2"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    stdout = process.stdout
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=lambda: [lines.put(line) for line in stdout])
    reader.start()
    shown: list[str] = []
    try:
        process.stdin.write("p value\n")
        process.stdin.flush()
        # The answer shows only while the recipe still waits on the debugger, before its rule finishes.
        while not shown or shown[-1] != "(Pdb) 42\n":
            shown.append(lines.get(timeout=30))
        process.stdin.write("c\n")
        process.stdin.close()
        status = process.wait(timeout=30)
    finally:
        process.kill()
        reader.join()
    shown.extend(lines.queue)

    assert status == 0, process.stderr.read()
    held = shown.index("before\n")
    released = shown.index("command\n")
    assert shown[released - 1] == "(Pdb) after\n"
    assert "other\n" in shown
    assert "other\n" not in shown[held:released]


@pytest.mark.project("breakpoint")
def test_breakpoint_disabled_by_pythonbreakpoint_leaves_a_rules_output_captured(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONBREAKPOINT", "0")

    result = run_fac(root, "-j", "1", "debugged")

    assert result.status == 0, result.err
    assert result.out == "before\nafter\ncommand\n"
