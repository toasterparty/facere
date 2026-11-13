"""Facere can't see what a recipe writes, so it checks for the damage an undeclared write does to the outputs an invocation built."""

from pathlib import Path

import pytest

from ..helpers import Fac


@pytest.mark.project("damaged_input")
def test_input_changed_after_its_rule_finished_fails_its_reader_without_executing_it(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:16:2: error: rule 'consume' (build/copy.txt) failed: its input build/a.txt changed after rule 'generate' (build/a.txt) finished",
        "fac.py:4:2: note: rule 'generate' (build/a.txt) outputs build/a.txt",
    ]
    assert not (root / "build" / "copy.txt").exists()


@pytest.mark.project("tampered")
def test_output_changed_after_its_rule_finished_fails_the_invocation(fac: Fac) -> None:
    result = fac("tamper")

    assert result.status == 1
    assert result.err == (
        "fac.py:6:2: error: rule 'copy' (build/a.txt) failed: its output build/a.txt changed after it finished\n"
    )


@pytest.mark.project("tampered")
def test_output_changed_after_its_rule_finished_is_rebuilt_next(root: Path, fac: Fac) -> None:
    fac("tamper")

    assert fac("copy").err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "hi"


@pytest.mark.project("tampered")
def test_output_deleted_after_its_rule_finished_passes(fac: Fac) -> None:
    result = fac("copy", "clean")

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 1 task and 1 rule.\n"


@pytest.mark.project("tampered")
def test_invocation_that_builds_nothing_checks_no_output(fac: Fac) -> None:
    fac("copy")

    result = fac("tamper")

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 1 task. 1 output up to date.\n"
