"""What a command sees of the terminal Facere runs on: a rule's command gets a terminal of its own as stderr alone, while a task's commands, and those of a rule declared with terminal=True, share Facere's."""

import ast
import sys
from pathlib import Path

import pytest

from ..helpers import mask_elapsed, run_fac
from .terminal import COLUMNS, ROWS, read_all, start_on_terminal

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no terminal for stderr alone"
)


def _probe(root: Path, target: str, name: str) -> tuple[object, str]:
    process, master = start_on_terminal(root, target)
    shown = mask_elapsed(read_all(master))
    assert process.wait(timeout=30) == 0, shown
    return ast.literal_eval((root / "build" / name).read_text()), shown


@pytest.mark.project("probe")
def test_rule_command_gets_a_terminal_as_stderr_alone_sized_as_facere_and_unable_to_prompt(
    root: Path,
) -> None:
    facts, shown = _probe(root, "rule_command", "rule.txt")

    # stdin, stdout, stderr a terminal, a controlling terminal, the size, output processing.
    assert facts == [False, False, True, False, (COLUMNS, ROWS), False]
    assert "to stderr\r\n" in shown


@pytest.mark.project("probe")
def test_rule_declared_with_terminal_shares_facere_standard_streams(root: Path) -> None:
    facts, _ = _probe(root, "terminal_command", "terminal.txt")

    assert facts == [True, True, True, False, (COLUMNS, ROWS), True]


@pytest.mark.project("probe")
def test_task_command_shares_facere_standard_streams(root: Path) -> None:
    facts, _ = _probe(root, "task_command", "task.txt")

    assert facts == [True, True, True, False, (COLUMNS, ROWS), True]


@pytest.mark.project("probe")
def test_rule_command_without_a_terminal_writes_stderr_to_a_pipe(root: Path) -> None:
    assert run_fac(root, "rule_command").status == 0

    facts = ast.literal_eval((root / "build" / "rule.txt").read_text())
    assert facts == [False, False, False, False, None, None]
