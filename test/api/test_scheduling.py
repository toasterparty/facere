"""Scheduling: rules executing at once, pools, what a failure leaves to build, tasks executing alone with the project loaded again after each, and each rule's output printed whole."""

from pathlib import Path

import pytest

from ..helpers import Fac

SERIAL_LOG = "start a\nend a\nstart b\nend b\nstart c\nend c\n"


@pytest.mark.project("overlap")
def test_rules_that_do_not_depend_on_each_other_execute_at_once(root: Path, fac: Fac) -> None:
    result = fac("-j2")

    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "a.txt").read_text() == "a"
    assert (root / "build" / "b.txt").read_text() == "b"


@pytest.mark.project("turns")
def test_one_job_executes_rules_one_at_a_time_in_the_order_defined(root: Path, fac: Fac) -> None:
    result = fac("-j1", "step")

    assert result.err == "Finished in <elapsed>. Executed 3 rules.\n"
    assert (root / "build" / "log.txt").read_text() == SERIAL_LOG


@pytest.mark.project("turns")
def test_pool_of_one_executes_its_rules_one_at_a_time_whatever_the_jobs(
    root: Path, fac: Fac
) -> None:
    result = fac("-j3", "link")

    assert result.err == "Finished in <elapsed>. Executed 3 rules.\n"
    assert (root / "build" / "log.txt").read_text() == SERIAL_LOG


@pytest.mark.project("bad_pool")
def test_pool_option_given_anything_but_a_pool_fails_collection(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: pool= takes what fac.pool returned, not 2",
        "Failed after <elapsed>.",
    ]


@pytest.mark.parametrize("jobs", ["0", "-1", "many"])
def test_jobs_takes_a_positive_count_or_auto(jobs: str, root: Path, fac: Fac) -> None:
    (root / "fac.py").write_text("")

    assert fac(f"--jobs={jobs}").status == 2
    assert fac("--jobs", "auto").status == 0


@pytest.mark.project("grouped")
def test_each_rule_prints_whole_what_its_recipe_and_commands_wrote_in_order(fac: Fac) -> None:
    result = fac("-j2")

    assert result.status == 0, result.err
    assert result.out in ("a 1\na 2\nb 1\nb 2\n", "b 1\nb 2\na 1\na 2\n")
    assert result.err in (
        "a 3\nb 3\nFinished in <elapsed>. Executed 2 rules.\n",
        "b 3\na 3\nFinished in <elapsed>. Executed 2 rules.\n",
    )


@pytest.mark.project("keep_going_task")
def test_keep_going_executes_a_task_only_where_the_rules_it_inputs_succeeded(fac: Fac) -> None:
    result = fac("-k", "needs_broken", "needs_fine")

    assert result.status == 1
    assert result.out == "needs_fine ran\n"
    assert result.err.splitlines()[-2:] == [
        "fac.py:4:2: error: rule 'broken' (build/broken.txt) failed",
        "Failed after <elapsed>. Executed 1 task and 1 rule.",
    ]


@pytest.mark.project("keep_going_task")
def test_failure_ends_the_invocation_before_the_targets_after_it(fac: Fac) -> None:
    result = fac("needs_broken", "needs_fine")

    assert result.status == 1
    assert result.out == ""
    assert result.err.splitlines()[-1] == "Failed after <elapsed>."


@pytest.mark.project("recollect")
def test_glob_lists_a_file_that_a_task_among_the_targets_created(root: Path, fac: Fac) -> None:
    result = fac("count", "add_page", "count")

    assert result.err == "Finished in <elapsed>. Executed 1 task and 2 rules.\n"
    assert (root / "build" / "count.txt").read_text() == "2"


@pytest.mark.project("recollect")
def test_constant_holds_what_a_task_among_the_targets_wrote(root: Path, fac: Fac) -> None:
    result = fac("stamp", "bump", "stamp")

    assert result.err == "Finished in <elapsed>. Executed 1 task and 2 rules.\n"
    assert (root / "build" / "version.txt").read_text() == "2"


@pytest.mark.project("recollect")
def test_source_a_task_edits_is_read_again_by_the_targets_after_it(root: Path, fac: Fac) -> None:
    result = fac("copy", "edit_page", "copy")

    assert result.err == "Finished in <elapsed>. Executed 1 task and 2 rules.\n"
    assert (root / "build" / "a.txt").read_text() == "edited"


@pytest.mark.project("recollect")
def test_project_is_loaded_once_where_no_target_follows_the_task(root: Path, fac: Fac) -> None:
    (root / "fac.py").write_text(
        (root / "fac.py").read_text() + "\nprint('loaded')\n", encoding="utf-8"
    )

    result = fac("count", "add_page")

    assert result.status == 0, result.err
    assert result.out == "loaded\n"


@pytest.mark.project("terminal_rule")
def test_live_rule_command_fails_at_once_without_a_terminal_naming_its_rule(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 1
    lines = result.err.splitlines()
    assert lines[0] == "Traceback (most recent call last):"
    assert lines[-3].startswith("RuntimeError: ")
    assert lines[-2:] == [
        "fac.py:6:2: error: rule 'sign' (build/signed.txt) failed",
        "Failed after <elapsed>.",
    ]
    assert not (root / "build" / "signed.txt").exists()


def _fail_building_recipe(*_: object) -> None:
    raise RuntimeError("engine bug")


@pytest.mark.project("crash")
def test_bug_in_facere_on_a_rules_worker_ends_the_invocation_as_a_crash(
    fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("facere._build._Builder._build_recipe", _fail_building_recipe)

    result = fac("page")

    assert result.status == 4
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: engine bug",
        "fac: error: Facere itself raised this, which is a bug in Facere",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("crash")
def test_bug_in_facere_on_a_tasks_thread_ends_the_invocation_as_a_crash(
    fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("facere._build._Builder._build_recipe", _fail_building_recipe)

    result = fac("show")

    assert result.status == 4
    assert result.out == ""
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: engine bug",
        "fac: error: Facere itself raised this, which is a bug in Facere",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("crash")
def test_file_error_while_answering_the_engine_fails_the_rule_and_ends_the_invocation(
    fac: Fac, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_recording(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("facere._build._Builder._record", fail_recording)

    result = fac("page")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'page' (build/page.txt) failed: disk full",
        "Failed after <elapsed>.",
    ]
