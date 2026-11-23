"""Facere's own streams, which a rule's live command holds while other output waits."""

import io

import pytest

from facere._output import Output

from ..helpers import Fac


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
