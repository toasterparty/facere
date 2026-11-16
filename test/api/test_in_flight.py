"""What holds while another rule's writes are in flight: each rule is checked against its own inputs and its own recipe, and none is recorded for a file that moved under it."""

from pathlib import Path

import pytest

from ..helpers import Fac


@pytest.mark.project("seen_earlier")
def test_input_changed_since_the_invocation_first_saw_it_leaves_its_reader_stale(
    root: Path, fac: Fac
) -> None:
    assert fac("-j1").err == "Finished in <elapsed>. Executed 3 rules.\n"
    assert (root / "build" / "copy.txt").read_text() == "edited"
    (root / "src.txt").write_text("first")

    result = fac("-j1", "copy")

    assert result.err == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date.\n"
    assert (root / "build" / "copy.txt").read_text() == "first"


@pytest.mark.project("checked_meanwhile")
def test_another_rules_check_of_an_output_hides_no_change_from_the_rule_reporting_it(
    fac: Fac,
) -> None:
    assert fac("-j3").err == "Finished in <elapsed>. Executed 4 rules.\n"

    result = fac("-j3")

    assert result.err == "Finished in <elapsed>. Executed 2 rules. 2 outputs up to date.\n"


@pytest.mark.project("damaged_meanwhile")
def test_input_damaged_while_its_reader_executes_fails_the_invocation_and_leaves_the_reader_stale(
    root: Path, fac: Fac
) -> None:
    result = fac("-j2")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:16:2: error: rule 'write' (build/x.txt) failed: its output build/x.txt changed after it finished",
        "Failed after <elapsed>. Executed 3 rules.",
    ]
    assert (root / "build" / "reader.txt").read_text() == "damaged"

    assert fac("-j2").err == "Finished in <elapsed>. Executed 2 rules. 1 output up to date.\n"
    assert (root / "build" / "reader.txt").read_text() == "good"


@pytest.mark.project("own_inputs")
def test_rules_executing_at_once_are_each_checked_against_their_own_inputs(
    root: Path, fac: Fac
) -> None:
    result = fac("-j2")

    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "a.txt").read_text() == "a"
    assert (root / "build" / "b.txt").read_text() == "b"


@pytest.mark.project("shadowed_meanwhile")
def test_file_new_in_a_directory_output_leaves_stale_a_rule_executing_that_read_its_name(
    fac: Fac,
) -> None:
    assert fac("-j2").err == "Finished in <elapsed>. Executed 3 rules.\n"

    assert fac("-j2").err == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date.\n"
    assert fac("-j2").err == "Finished in <elapsed>. No work to do. 3 outputs up to date.\n"


@pytest.mark.project("unsettled_order")
def test_warning_for_rules_that_stay_stale_names_the_one_defined_first(fac: Fac) -> None:
    assert fac("-j2").err == "Finished in <elapsed>. Executed 2 rules.\n"

    result = fac("-j2")

    assert result.err == (
        "fac.py:17:2: warning: rule 'tidy_a' (build/a.out) stays stale: a.txt changed while its recipe executed, in this execution and its last, as for 1 more rule\n"
        "Finished in <elapsed>. Executed 2 rules.\n"
    )
