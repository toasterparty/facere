"""Facere's own streams, which a rule's live command holds while other output waits."""

import io

from facere._output import Output


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
