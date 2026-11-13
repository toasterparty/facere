"""What a recipe reports through fac.add_inputs joins its rule's record, and fac.OrderOnly orders what it may report."""

import os
import shutil
import sys
from pathlib import Path

import pytest

from ..helpers import Fac, edit

EXECUTED_ONE = "Finished in <elapsed>. Executed 1 rule.\n"
UP_TO_DATE_ONE = "Finished in <elapsed>. No work to do. 1 output up to date.\n"

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="needs symlinks and file modes")


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
    assert "scratch.h, which it then removed" in result.err


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
def test_new_order_only_path_reruns_the_rule_though_no_content_changed(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", "HEADERS = [GENERATED]", 'HEADERS = [GENERATED, "spec.txt"]')

    assert fac().err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"


@pytest.mark.project("order_only_unread")
def test_new_order_only_path_reruns_no_rule_whose_recipe_never_names_the_parameter(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", 'GENERATED = ["a.h"]', 'GENERATED = ["a.h", "b.h"]')

    assert fac().err == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date.\n"
    assert (root / "build" / "b.h").read_text() == "generated"


@pytest.mark.project("order_only_unread")
def test_recipe_calling_locals_counts_as_naming_every_parameter(root: Path, fac: Fac) -> None:
    edit(root / "fac.py", '"compiled"', 'str(len(locals()["headers"]))')
    fac()
    edit(root / "fac.py", 'GENERATED = ["a.h"]', 'GENERATED = ["a.h", "b.h"]')

    assert fac().err == "Finished in <elapsed>. Executed 2 rules. 1 output up to date.\n"
    assert (root / "build" / "main.o").read_text() == "2"


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
def test_report_outside_the_root_makes_the_rule_stale_when_it_changes(root: Path, fac: Fac) -> None:
    fac("-C", "project", "compile")
    (root / "sdk" / "stdlib.h").write_text("upgraded")

    assert fac("-C", "project", "compile").err == EXECUTED_ONE


@pytest.mark.project("outside_root")
def test_new_file_named_as_a_report_outside_the_root_makes_the_rule_stale_once(
    root: Path, fac: Fac
) -> None:
    fac("-C", "project", "compile")
    assert fac("-C", "project", "compile").err == UP_TO_DATE_ONE

    (root / "project" / "stdlib.h").write_text("shadow")

    assert fac("-C", "project", "compile").err == EXECUTED_ONE
    assert fac("-C", "project", "compile").err == UP_TO_DATE_ONE


@pytest.mark.project("outside_root")
def test_new_file_named_otherwise_leaves_the_rule_up_to_date(root: Path, fac: Fac) -> None:
    fac("-C", "project", "compile")

    (root / "project" / "unrelated.h").write_text("new")

    assert fac("-C", "project", "compile").err == UP_TO_DATE_ONE


@pytest.mark.project("outside_root")
def test_new_file_in_a_hidden_directory_is_never_listed(root: Path, fac: Fac) -> None:
    fac("-C", "project", "compile")

    (root / "project" / ".hidden").mkdir()
    (root / "project" / ".hidden" / "stdlib.h").write_text("shadow")

    assert fac("-C", "project", "compile").err == UP_TO_DATE_ONE


@pytest.mark.project("outside_root")
def test_invocation_that_skips_the_shadowed_rule_keeps_it_stale(root: Path, fac: Fac) -> None:
    fac("-C", "project", "compile")

    (root / "project" / "stdlib.h").write_text("shadow")
    assert fac("-C", "project", "other").err == EXECUTED_ONE

    assert fac("-C", "project", "compile").err == EXECUTED_ONE


@pytest.mark.project("in_tree_scratch")
def test_file_a_recipe_writes_under_the_root_does_not_count_as_new(fac: Fac) -> None:
    assert fac().err == EXECUTED_ONE
    assert fac().err == UP_TO_DATE_ONE


@pytest.mark.project("fails_after_recording")
def test_a_failed_invocation_leaves_no_false_shadow_for_the_next(root: Path, fac: Fac) -> None:
    assert fac().status == 1

    (root / "ok.txt").write_text("ok")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"


@pytest.mark.project("first_report")
def test_file_changed_after_the_tool_read_it_and_before_its_first_report_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    assert (root / "a.h").read_text() == "new"
    assert (root / "build" / "bundle.txt").read_text() == "old"

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "bundle.txt").read_text() == "new"
    assert fac().err == UP_TO_DATE_ONE


@pytest.mark.project("output_first_reported")
def test_output_first_reported_by_the_rule_ordered_after_it_leaves_that_rule_up_to_date(
    fac: Fac,
) -> None:
    fac()

    assert fac().err == "Finished in <elapsed>. No work to do. 2 outputs up to date.\n"


@pytest.mark.project("tool_written_report")
def test_reported_file_a_command_writes_outside_the_output_directory_never_settles(
    fac: Fac,
) -> None:
    assert fac().err == EXECUTED_ONE

    assert fac().err.splitlines() == [
        "fac.py:9:2: warning: rule 'parser' (build/parser.o) stays stale: parser.h changed while its recipe executed, in this execution and its last",
        "Finished in <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("own_scratch")
def test_reported_scratch_file_the_recipe_rewrites_settles_after_one_execution(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "grammar.y").write_text("b")

    assert fac().err == EXECUTED_ONE
    assert fac().err == UP_TO_DATE_ONE


@posix_only
@pytest.mark.project("linked_root")
def test_report_resolved_through_a_link_to_the_root_tracks_the_file(root: Path, fac: Fac) -> None:
    os.symlink(root / "project", root / "link")
    fac("-C", "link")
    (root / "project" / "a.h").write_text("edited")

    assert fac("-C", "link").err == EXECUTED_ONE
    assert (root / "project" / "build" / "bundle.txt").read_text() == "edited"


@pytest.mark.skipif(sys.platform != "linux", reason="needs a file system that tells case apart")
@pytest.mark.project("case")
def test_reported_files_differing_only_in_case_are_both_tracked(root: Path, fac: Fac) -> None:
    (root / "dscp.h").write_text("lower")
    (root / "DSCP.h").write_text("upper")
    fac()
    (root / "dscp.h").write_text("edited")

    assert fac().err == EXECUTED_ONE
    assert (root / "build" / "bundle.txt").read_text() == "edited upper"


@pytest.mark.project("adopted")
def test_recorded_report_another_rule_starts_to_output_fails_naming_both(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", "GENERATED = []", 'GENERATED = [{"header": "include/config.h"}]')

    result = fac()

    assert result.status == 1
    assert "rule 'configure' (include/config.h) outputs include/config.h" in result.err


@pytest.mark.project("new_output")
def test_new_output_named_as_a_reported_file_makes_the_rule_stale(root: Path, fac: Fac) -> None:
    fac()
    assert (root / "build" / "main.o").read_text() == "hand"
    edit(root / "fac.py", 'GENERATED = ["version.h"]', 'GENERATED = ["version.h", "config.h"]')

    fac()

    assert (root / "build" / "main.o").read_text() == "generated"


@pytest.mark.project("new_in_directory_output")
def test_file_new_in_a_directory_output_named_as_a_reported_file_makes_the_rule_stale(
    root: Path, fac: Fac
) -> None:
    fac()
    assert (root / "build" / "main.o").read_text() == "hand"
    edit(root / "fac.py", 'GENERATED = ["version.h"]', 'GENERATED = ["version.h", "config.h"]')

    fac()

    assert (root / "build" / "main.o").read_text() == "generated"


@pytest.mark.project("output_rewritten_by_tool")
def test_rule_output_a_command_rewrites_as_it_was_before_its_first_report_never_settles(
    fac: Fac,
) -> None:
    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"

    assert fac().err.splitlines() == [
        "fac.py:15:2: warning: rule 'compile' (build/main.o) stays stale: build/gen.h changed while its recipe executed, in this execution and its last",
        "Finished in <elapsed>. Executed 1 rule. 1 output up to date.",
    ]


@pytest.mark.project("hidden_report")
def test_file_first_reported_from_a_hidden_directory_settles_after_one_execution(
    fac: Fac,
) -> None:
    assert fac().err == EXECUTED_ONE

    assert fac().err == UP_TO_DATE_ONE


@posix_only
@pytest.mark.project("linked_report")
def test_file_first_reported_behind_a_linked_directory_settles_after_one_execution(
    root: Path, fac: Fac
) -> None:
    os.symlink("real", root / "vendor")
    assert fac().err == EXECUTED_ONE

    assert fac().err == UP_TO_DATE_ONE


@pytest.mark.project("directory_report")
def test_reporting_a_directory_fails_naming_it(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert "IsADirectoryError" in result.err
    assert "'include'" in result.err
