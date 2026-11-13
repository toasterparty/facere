"""Which rules execute: a rule is stale without a record, with a changed fingerprint, or with a missing or changed output."""

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from ..helpers import Fac, edit, run_fac

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="needs symlinks and file modes")


@pytest.mark.project("shout")
def test_first_build_executes_the_rule(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HI!"


@pytest.mark.project("shout")
def test_second_build_executes_nothing(fac: Fac) -> None:
    fac()

    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("project_env")
def test_changed_project_env_reruns_every_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", 'LC_ALL="C"', 'LC_ALL="C.UTF-8"')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("sources")
def test_file_a_sources_glob_newly_matches_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    (root / "pages" / "b.md").write_text("b")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "index.txt").read_text() == "pages/a.md pages/b.md"


@pytest.mark.project("shout")
def test_changed_input_content_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    (root / "a.txt").write_text("ho")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HO!"


@pytest.mark.project("shout")
def test_changed_recipe_code_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "text.upper()", "text.title()")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "Hi!"


@pytest.mark.project("shout")
def test_comments_docstrings_and_reformatting_rerun_nothing(root: Path, fac: Fac) -> None:
    fac()
    edit(
        root / "fac.py",
        "    with open(source",
        '    """Shout the source."""\n    # read it\n    with open(\n        source',
    )
    edit(root / "fac.py", "@fac.rule(default=True)", "# the only rule\n@fac.rule(default = True)")

    result = fac()

    assert result.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("shout")
def test_changed_global_the_recipe_reads_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", 'SUFFIX = "!"', 'SUFFIX = "?"')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HI?"


@pytest.mark.project("shout")
def test_changed_global_the_recipe_never_reads_reruns_nothing(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "UNREAD = 1", "UNREAD = 2")

    result = fac()

    assert result.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("shout")
def test_changed_parameter_value_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "times=1", "times=2")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HIHI!"


@pytest.mark.project("closure")
def test_changed_closure_variable_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", 'define("!")', 'define("?")')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "hi?"


@pytest.mark.project("helpers")
def test_changed_helper_the_recipe_calls_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "text.strip()", "text.strip().lower()")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("helpers")
def test_changed_function_a_helper_calls_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", 'text + "!"', 'text + "?"')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "*HI?*"


@pytest.mark.project("helpers")
def test_changed_method_of_a_class_the_recipe_uses_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "text.upper()", "text.title()")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "*Hi!*"


@pytest.mark.project("helpers")
def test_changed_shared_module_function_the_recipe_calls_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "textutil.py", "MARK + text + MARK", "MARK + text")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "*HI!"


@pytest.mark.project("helpers")
def test_changed_shared_module_constant_a_helper_reads_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "textutil.py", 'MARK = "*"', 'MARK = "_"')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "_HI!_"


@pytest.mark.project("helpers")
def test_shared_module_edit_keeping_size_and_mtime_runs_the_new_code(root: Path, fac: Fac) -> None:
    fac()
    path = root / "textutil.py"
    before = path.stat()
    edit(path, 'MARK = "*"', 'MARK = "_"')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "_HI!_"


@pytest.mark.project("helpers")
def test_shared_module_edit_keeping_size_and_mtime_runs_the_new_code_when_python_trusts_hashes(
    root: Path,
) -> None:
    trusting = ("--check-hash-based-pycs", "never")
    for _ in range(2):
        assert run_fac(root, python_flags=trusting).status == 0
    path = root / "textutil.py"
    before = path.stat()
    edit(path, 'MARK = "*"', 'MARK = "_"')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    result = run_fac(root, python_flags=trusting)

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "_HI!_"


@pytest.mark.project("helpers")
def test_changed_shared_module_code_the_recipe_never_reaches_reruns_nothing(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "textutil.py", "UNREAD = 1", "UNREAD = 2")
    edit(root / "textutil.py", "return text\n", "return text * 2\n")
    edit(
        root / "fac.py",
        "def exclaim(text):",
        'def exclaim(text):\n    # add the mark\n    """Exclaim."""',
    )

    result = fac()

    assert result.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("two_outputs")
def test_outputs_swapped_between_parameters_rerun_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(
        root / "fac.py",
        '{"first": fac.out("x"), "second": fac.out("y")}',
        '{"first": fac.out("y"), "second": fac.out("x")}',
    )

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "x").read_text() == "second"


@pytest.mark.project("shout")
def test_deleted_output_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    (root / "build" / "a.txt").unlink()

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HI!"


@pytest.mark.project("shout")
def test_output_edited_by_hand_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    (root / "build" / "a.txt").write_text("edited")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HI!"


@pytest.mark.project("shout")
def test_lost_state_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    shutil.rmtree(root / "build" / ".fac")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("shout")
def test_unreadable_state_counts_as_lost(root: Path, fac: Fac) -> None:
    fac()
    (root / "build" / ".fac" / "state.db").write_bytes(b"not a database")

    first = fac()
    second = fac()

    assert first.status == 0, first.err
    assert first.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert second.status == 0, second.err
    assert second.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("shout")
def test_unwritable_state_fails_the_rule_naming_the_database(root: Path, fac: Fac) -> None:
    fac()
    (root / "a.txt").write_text("ho")
    os.chmod(root / "build" / ".fac" / "state.db", stat.S_IREAD)

    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:7:2: error: rule 'shout' (build/a.txt) failed: build/.fac/state.db: attempt to write a readonly database",
    ]


@pytest.mark.project("touch")
def test_unwritable_state_holding_an_undeclared_output_fails_before_building(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", '"x.txt"', '"y.txt"')
    os.chmod(root / "build" / ".fac" / "state.db", stat.S_IREAD)

    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac: error: build/.fac/state.db: attempt to write a readonly database",
    ]
    assert not (root / "build" / "y.txt").exists()


@pytest.mark.project("downstream")
def test_downstream_rule_reruns_only_when_an_input_it_reads_changes_content(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", "out.write(file.read())", "out.write(file.read() + '')")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"


@pytest.mark.project("shout")
def test_failed_rule_leaves_no_record(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "    with open(source", "    assert False\n    with open(source")
    assert fac().status == 1
    edit(root / "fac.py", "    assert False\n", "")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("forget")
def test_recipe_succeeding_without_writing_its_output_fails(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'forget' (build/never.txt) failed: its recipe succeeded without writing build/never.txt",
    ]


@pytest.mark.project("deep_output")
def test_outputs_parent_directories_exist_before_the_recipe_runs(root: Path, fac: Fac) -> None:
    result = fac()

    assert result.status == 0
    assert (root / "build" / "a" / "b" / "c.txt").is_file()


@pytest.mark.project("append")
def test_existing_output_stays_in_place_when_its_rule_executes(root: Path, fac: Fac) -> None:
    fac()
    (root / "a.txt").write_text("2")

    fac()

    assert (root / "build" / "log.txt").read_text() == "12"


@pytest.mark.project("leftover")
def test_recipe_that_stops_writing_its_output_records_what_an_earlier_execution_left(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "spec.txt").write_text("")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "services.h").read_text() == "service"


@pytest.mark.project("orphan")
def test_input_no_rule_outputs_anymore_is_a_source_once_an_earlier_build_left_it(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", 'HEADER = fac.out("gen/old.h")', 'HEADER = fac.out("gen/new.h")')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"
    assert (root / "build" / "main.o").read_text() == "one"


@pytest.mark.project("touch")
def test_record_of_an_output_no_rule_declares_is_dropped(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", '"x.txt"', '"y.txt"')
    fac()
    edit(root / "fac.py", '"y.txt"', '"x.txt"')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("directory_input")
def test_directory_input_is_hashed_by_its_tree(root: Path, fac: Fac) -> None:
    fac()
    unchanged = fac()
    (root / "pages" / "b.md").write_text("b")

    added = fac()

    assert unchanged.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"
    assert added.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "index.txt").read_text() == "a.md b.md"


@pytest.mark.project("directory_output")
def test_directory_output_edited_by_hand_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    unchanged = fac()
    (root / "build" / "site" / "index.html").write_text("edited")

    edited = fac()

    assert unchanged.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"
    assert edited.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "site" / "index.html").read_text() == "<p>hi</p>"


@pytest.mark.project("shout")
def test_task_executes_on_every_build_after_the_rules_it_inputs(fac: Fac) -> None:
    first = fac("show")
    second = fac("show")

    assert first.out == "HI!\n"
    assert first.err == "Finished in <elapsed>. Executed 1 task and 1 rule.\n"
    assert second.out == "HI!\n"
    assert second.err == "Finished in <elapsed>. Executed 1 task. 1 output up to date.\n"


@pytest.mark.project("reverted")
def test_input_changed_during_the_recipe_then_changed_back_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "two"

    (root / "a.txt").write_text("one")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "one"


@pytest.mark.project("rewrites_input")
def test_rule_whose_recipe_rewrites_its_input_warns_from_its_second_execution(fac: Fac) -> None:
    assert fac("build/a.txt").err == "Finished in <elapsed>. Executed 1 rule.\n"

    assert fac("build/a.txt").err.splitlines() == [
        "fac.py:7:2: warning: rule 'tidy' (build/a.txt) stays stale: a.txt changed while its recipe executed, in this execution and its last",
        "Finished in <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("rewrites_input")
def test_rules_that_stay_stale_together_share_one_warning(fac: Fac) -> None:
    fac()

    assert fac().err.splitlines() == [
        "fac.py:7:2: warning: rule 'tidy' (build/a.txt) stays stale: a.txt changed while its recipe executed, in this execution and its last, as for 1 more rule",
        "Finished in <elapsed>. Executed 2 rules.",
    ]


@pytest.mark.project("helper_default")
def test_changed_constant_a_helper_takes_as_a_default_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", 'MARK = "!"', 'MARK = "?"')

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "hi?"


@pytest.mark.project("wrapped_helper")
def test_changed_helper_behind_a_standard_library_decorator_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", 'file.write("hi")', 'file.write("ho")')

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "ho!"


@pytest.mark.project("base_class")
def test_changed_method_a_class_inherits_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "text.upper()", "text.title()")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "Hi"


@pytest.mark.project("held_value")
def test_changed_method_of_a_class_a_value_holds_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", "text.upper()", "text.title()")

    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "a.txt").read_text() == "Hi!#*+?~"


@pytest.mark.project("held_value")
def test_value_holding_a_set_hashes_alike_under_any_hash_seed(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONHASHSEED", "1")
    assert run_fac(root).status == 0
    monkeypatch.setenv("PYTHONHASHSEED", "2")

    result = run_fac(root)

    assert result.err == "Finished in <elapsed>. No work to do. 2 outputs up to date.\n"


@pytest.mark.project("pattern_default")
def test_sentinel_and_compiled_pattern_defaults_rerun_nothing_unchanged(fac: Fac) -> None:
    fac()

    assert fac().err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.project("pattern_default")
def test_changed_pattern_a_helper_compiles_as_a_default_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", 'PATTERN = r"\\s+"', 'PATTERN = r"\\s"')

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("int_enum")
def test_constant_changed_from_an_int_enum_member_to_its_int_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", "LEVEL = Level.LOW", "LEVEL = 1")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"


@pytest.mark.project("lambda_helper")
def test_changed_lambda_helper_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    edit(root / "fac.py", '+ "!"', '+ "?"')

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "a.txt").read_text() == "HI?"


@posix_only
@pytest.mark.project("linked_page")
def test_changed_target_of_a_link_inside_a_directory_input_reruns_the_rule(
    root: Path, fac: Fac
) -> None:
    os.symlink("../shared/logo.md", root / "pages" / "logo.md")
    fac()
    (root / "shared" / "logo.md").write_text("edited")

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "index.txt").read_text() == "a edited"


@posix_only
@pytest.mark.project("executable")
def test_input_made_executable_reruns_the_rule(root: Path, fac: Fac) -> None:
    fac()
    (root / "tool.sh").chmod(0o755)

    assert fac().err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert os.access(root / "build" / "tool.sh", os.X_OK)


@pytest.mark.project("inside_directory")
def test_input_inside_a_directory_output_builds_the_rule_outputting_the_directory(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "main.o").read_text() == "one"


@pytest.mark.project("always")
def test_rule_marked_always_executes_whenever_reached_and_its_reader_only_on_a_change(
    fac: Fac,
) -> None:
    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"

    assert fac().err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"


@pytest.mark.project("always")
def test_reader_of_a_rule_marked_always_executes_when_its_output_changes(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / ".tool" / "version").write_text("2.0")

    assert fac().err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "app.txt").read_text() == "built with 2.0"
