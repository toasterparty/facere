"""What a recipe reports through fac.add_inputs joins its rule's record, and fac.OrderOnly orders what it may report."""

import shutil
from pathlib import Path

import pytest

from ..helpers import Fac, edit

EXECUTED_ONE = "Finished in <elapsed>. Executed 1 rule.\n"
UP_TO_DATE_ONE = "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("report")
def test_editing_a_reported_file_reruns_the_rule(root: Path, fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE
    assert fac().err == UP_TO_DATE_ONE

    (root / "a.h").write_text("edited")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "bundle.txt").read_text() == "edited"


@pytest.mark.project("report")
def test_a_file_the_last_report_omits_stops_counting(root: Path, fac: Fac) -> None:
    fac()
    (root / "listing.txt").write_text("b.h\n")
    assert fac().err == EXECUTED_ONE

    (root / "a.h").write_text("edited")

    assert fac().err == UP_TO_DATE_ONE


@pytest.mark.project("report")
def test_a_reported_file_deleted_later_makes_the_rule_stale_rather_than_failing(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "a.h").unlink()
    (root / "listing.txt").write_text("b.h\n")

    result = fac()

    assert result.status == 0, result.err
    assert result.err == EXECUTED_ONE
    assert (root / "build" / "bundle.txt").read_text() == "b"


@pytest.mark.project("report")
def test_losing_the_state_costs_a_rebuild(root: Path, fac: Fac) -> None:
    fac()
    shutil.rmtree(root / "build" / ".fac")

    assert fac().err == EXECUTED_ONE


@pytest.mark.project("report_after_tool")
def test_a_depfile_spelling_of_a_path_tracks_the_file(root: Path, fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE

    (root / "b.h").write_text("edited")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "bundle.txt").read_text() == "aedited"


@pytest.mark.project("declared_report")
def test_reporting_a_declared_input_changes_nothing(root: Path, fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE
    assert fac().err == UP_TO_DATE_ONE

    (root / "main.c").write_text("edited")

    assert fac().err == EXECUTED_ONE


@pytest.mark.project("changed_during_recipe")
def test_a_reported_file_changed_during_the_recipe_stays_stale(root: Path, fac: Fac) -> None:
    fac()
    (root / "a.h").write_text("edit-me")

    assert fac().err == EXECUTED_ONE
    assert (root / "a.h").read_text() == "edited"
    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "bundle.txt").read_text() == "edited"
    assert fac().err == UP_TO_DATE_ONE


@pytest.mark.project("missing_report")
def test_reporting_a_missing_file_fails_and_records_nothing(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert "absent.h" in result.err
    assert not (root / "build" / "bundle.txt").exists()


@pytest.mark.project("report_then_remove")
def test_removing_a_file_after_reporting_it_fails_the_rule(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert "build/scratch.h" in result.err


@pytest.mark.project("string_report")
def test_a_bare_string_is_not_a_list_of_paths(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert "TypeError" in result.err


@pytest.mark.project("task_reports")
def test_a_task_cannot_report_since_it_records_nothing(fac: Fac) -> None:
    result = fac("check")

    assert result.status == 1
    assert "RuntimeError" in result.err


@pytest.mark.project("order_only")
def test_order_only_input_builds_first_without_joining_the_fingerprint(
    root: Path, fac: Fac
) -> None:
    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"

    (root / "spec.txt").write_text("edited")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"
    assert (root / "build" / "main.o").read_text() == "unused"


@pytest.mark.project("order_only")
def test_order_only_input_counts_once_reported(root: Path, fac: Fac) -> None:
    (root / "listing.txt").write_text("build/gen.h\n")
    fac()
    assert (root / "build" / "main.o").read_text() == "spec"

    (root / "spec.txt").write_text("edited")

    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "main.o").read_text() == "edited"


@pytest.mark.project("order_only")
def test_new_order_only_path_alone_reruns_nothing(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "HEADERS = [GENERATED]", 'HEADERS = [GENERATED, "spec.txt"]')

    assert fac().err == "Finished in <elapsed>. No work to do. 2 outputs up to date.\n"


@pytest.mark.project("order_only_missing")
def test_order_only_source_must_exist(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err == (
        "fac.py:4:2: error: rule 'compile' (build/main.o) inputs absent.h, which doesn't exist, and no rule outputs it\n"
    )


@pytest.mark.project("order_only_cycle")
def test_order_only_input_can_close_a_cycle(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert "dependency cycle" in result.err


@pytest.mark.project("order_only_task")
def test_a_task_declaring_order_only_fails_collection(fac: Fac) -> None:
    result = fac("check")

    assert result.status == 2
    assert result.err.startswith("fac.py:9:2: error: task check declares a fac.OrderOnly input")


@pytest.mark.project("unordered")
def test_reporting_another_rules_output_it_does_not_input_fails_naming_both(fac: Fac) -> None:
    result = fac("generate", "racing")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:20:2: error: rule 'racing' (build/racing.o) failed: its recipe reported reading build/gen/gen.h, though no fac.Input or fac.OrderOnly parameter orders it after the rule that outputs it",
        "fac.py:8:2: note: rule 'generate' (build/gen) outputs build/gen/gen.h",
    ]


@pytest.mark.project("unordered")
def test_reporting_a_file_inside_a_directory_the_rule_inputs_passes(fac: Fac) -> None:
    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"


@pytest.mark.project("outside_root")
def test_new_file_named_as_a_dropped_report_makes_the_rule_stale_once(root: Path, fac: Fac) -> None:
    fac("compile")
    assert fac("compile").err == UP_TO_DATE_ONE

    (root / "stdlib.h").write_text("shadow")

    assert fac("compile").err == EXECUTED_ONE
    assert fac("compile").err == UP_TO_DATE_ONE


@pytest.mark.project("outside_root")
def test_new_file_named_otherwise_leaves_the_rule_up_to_date(root: Path, fac: Fac) -> None:
    fac("compile")

    (root / "unrelated.h").write_text("new")

    assert fac("compile").err == UP_TO_DATE_ONE


@pytest.mark.project("outside_root")
def test_new_file_in_a_hidden_directory_is_never_listed(root: Path, fac: Fac) -> None:
    fac("compile")

    (root / ".hidden").mkdir()
    (root / ".hidden" / "stdlib.h").write_text("shadow")

    assert fac("compile").err == UP_TO_DATE_ONE


@pytest.mark.project("outside_root")
def test_invocation_that_skips_the_shadowed_rule_keeps_it_stale(root: Path, fac: Fac) -> None:
    fac("compile")

    (root / "stdlib.h").write_text("shadow")
    assert fac("other").err == EXECUTED_ONE

    assert fac("compile").err == EXECUTED_ONE


@pytest.mark.project("in_tree_scratch")
def test_file_a_recipe_writes_under_the_root_does_not_count_as_new(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE
    assert fac().err == UP_TO_DATE_ONE


@pytest.mark.project("fails_after_recording")
def test_a_failed_invocation_leaves_no_false_shadow_for_the_next(root: Path, fac: Fac) -> None:
    assert fac().status == 1

    (root / "ok.txt").write_text("ok")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"
