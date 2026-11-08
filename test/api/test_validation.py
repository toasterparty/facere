"""Collection errors: each fails before any recipe executes, in GNU format, naming every definition involved and how to fix it."""

import sys
from pathlib import Path

import pytest

from ..helpers import Fac


@pytest.mark.project("case_clash")
def test_two_rules_outputting_one_path_compared_without_case_fail(root: Path, fac: Fac) -> None:
    result = fac("lower")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: 2 outputs claim build/x.txt, compared without case",
        "fac.py:4:2: note: rule 'lower' (build/x.txt) outputs build/x.txt",
        "fac.py:9:2: note: rule 'upper' (build/X.txt) outputs build/X.txt",
    ]
    assert not (root / "build" / "x.txt").exists()


@pytest.mark.project("args_misuse")
def test_args_parameter_outside_one_task_or_filled_by_a_keyword_fails(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule rule_args takes words, annotated fac.Args, but only a task receives the command line's arguments",
        "fac.py:9:2: error: task two_args takes 2 parameters annotated fac.Args, though only one receives the arguments after --",
        "fac.py:14:2: error: parameter words is annotated fac.Args, so only the command line fills it",
    ]


@pytest.mark.project("declared_in_shared_module")
def test_error_in_a_definition_a_module_declared_notes_the_decorator(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:1:1: error: starred takes *paths, which no rule or task can fill",
        "tools/tasks.py:4:2: note: declared here",
    ]


@pytest.mark.project("rule_without_output")
def test_rule_without_output_fails(fac: Fac) -> None:
    result = fac("nothing")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule nothing declares no output",
    ]


@pytest.mark.project("task_with_output")
def test_task_with_output_fails(fac: Fac) -> None:
    result = fac("report")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: task report declares an output, but a task writes no tracked output",
    ]


@pytest.mark.project("star_parameters")
def test_rule_taking_star_args_or_star_star_kwargs_fails(fac: Fac) -> None:
    result = fac("positional")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: positional takes *paths, which no rule or task can fill",
        "fac.py:9:2: error: keyword takes **options, which no rule or task can fill",
    ]


@pytest.mark.project("not_a_path")
def test_path_parameter_holding_no_path_fails_naming_its_annotation(fac: Fac) -> None:
    result = fac("copy")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: parameter source is annotated fac.Input but holds '', not a path",
        "fac.py:9:2: error: parameter pages is annotated list[fac.Input] but holds 'a.md', not a list of paths",
        "fac.py:14:2: error: parameter out is annotated fac.Output but holds '', not a path",
    ]


@pytest.mark.project("empty_name")
def test_empty_name_fails(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: the name '' can't be typed as a target",
        "fac.py:9:2: error: the name '' can't be typed as a target",
    ]


@pytest.mark.project("unreadable_annotation")
def test_annotation_facere_cannot_read_fails(fac: Fac) -> None:
    result = fac("optional")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:6:2: error: parameter source has an annotation Facere can't read, and reads only fac.Input, list[fac.Input], fac.OrderOnly, list[fac.OrderOnly], fac.Output, list[fac.Output], and fac.Args",
        "fac.py:11:2: error: can't read the annotations of undefined: NameError: name 'Missing' is not defined",
    ]


@pytest.mark.project("state_output")
def test_output_holding_the_state_fails(fac: Fac) -> None:
    result = fac("everything")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'everything' (build) outputs build, which holds Facere's state",
        "fac.py:9:2: error: rule 'inside' (build/.fac/a) outputs build/.fac/a, which holds Facere's state",
    ]


@pytest.mark.project("out_dir_input")
def test_rule_input_holding_the_output_directory_fails(fac: Fac) -> None:
    result = fac("tree")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'tree' (build/tree.tar) inputs ., which holds the output directory build, so its content changes on every build",
        "fac.py:9:2: error: rule 'build_dir' (build/build.tar) inputs build, which holds the output directory build, so its content changes on every build",
    ]


@pytest.mark.project("out_dir_input")
def test_root_input_passes_once_the_output_directory_lies_outside_the_root(fac: Fac) -> None:
    result = fac("--out", "../elsewhere", "tree")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:9:2: error: rule 'build_dir' (../elsewhere/build.tar) inputs ../elsewhere, which holds the output directory ../elsewhere, so its content changes on every build",
    ]


@pytest.mark.project("shared_function_name")
def test_two_functions_sharing_a_name_fail(fac: Fac) -> None:
    result = fac("docs")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: 2 definitions share the name docs",
        "fac.py:4:2: note: rule 'docs' (build/a) is defined here",
        "fac.py:9:2: note: rule 'docs' (build/b) is defined here",
    ]


@pytest.mark.project("shared_task_name")
def test_two_tasks_sharing_a_name_fail(fac: Fac) -> None:
    result = fac("greet")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:8:1: error: 2 definitions share the name greet",
        "fac.py:8:1: note: task 'greet' is defined here",
        "fac.py:9:1: note: task 'greet' is defined here",
    ]


@pytest.mark.project("no_value")
def test_parameter_without_value_fails(fac: Fac) -> None:
    result = fac("copy")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: parameter source has no value",
    ]


@pytest.mark.project("option_name")
def test_parameter_named_after_an_option_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: parameter always is named after a fac.rule option, so no keyword argument can fill it",
    ]


@pytest.mark.project("unhashable")
def test_value_facere_cannot_hash_fails_naming_its_type(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:6:2: error: function page reads global LOCK, of type object, which Facere can't hash, since Facere hashes only None, a bool, int, float, str, bytes, module, function, or class, or a tuple, list, dict, or set of them",
        "fac.py:6:2: error: rule 'page' (build/a) reads parameter lock, of type object, which Facere can't hash, since Facere hashes only None, a bool, int, float, str, bytes, module, function, or class, or a tuple, list, dict, or set of them",
    ]


@pytest.mark.project("pure_path")
def test_pathlib_path_value_fails_naming_string_paths(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:6:2: error: rule 'page' (build/a) reads parameter directory, of type pathlib.PurePosixPath, which Facere can't hash, since Facere paths are strings with /",
    ]


@pytest.mark.project("unreadable_source")
def test_rule_whose_source_facere_cannot_read_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.startswith(
        "fac.py:4:1: error: function page has no source Facere can read, which a rule's fingerprint needs: "
    )


@pytest.mark.project("unreadable_helper")
def test_rule_reaching_a_helper_whose_source_facere_cannot_read_fails(root: Path, fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        f"fac.py:6:2: error: function page reaches <lambda>, which has no source Facere can read, which a rule's fingerprint needs: found no source for <lambda> in {root / 'fac.py'}",
    ]


@pytest.mark.project("unannotated_file")
def test_unannotated_value_naming_a_file_under_the_root_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'page' (build/a) reads parameter source, which names the path notes.txt unannotated",
    ]


@pytest.mark.project("unannotated_output")
def test_unannotated_value_naming_a_path_a_rule_outputs_fails(fac: Fac) -> None:
    result = fac("index")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:9:2: error: rule 'index' (build/index.html) reads parameter pages, which names the path build/page.html unannotated",
    ]


@pytest.mark.project("global_path")
def test_global_naming_a_file_under_the_root_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:6:2: error: function page reads global NOTES, which names the path notes.txt",
    ]


@pytest.mark.project("helper_global_path")
def test_global_a_helper_reads_naming_a_file_under_the_root_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:11:2: error: function page reads global NOTES through read_notes, which names the path notes.txt",
    ]


@pytest.mark.project("scratch_path")
def test_unannotated_value_naming_a_scratch_file_in_the_output_directory_passes(fac: Fac) -> None:
    fac()

    result = fac()

    assert result.status == 0, result.err
    assert result.err == "Finished in <elapsed>. No work to do. 1 output up to date.\n"


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows separates paths with \\")
@pytest.mark.project("backslash_input")
def test_input_written_with_backslashes_matches_the_rule_outputting_it(
    root: Path, fac: Fac
) -> None:
    result = fac()

    assert result.status == 0, result.err
    assert (root / "build" / "b.txt").read_text() == "a"


@pytest.mark.project("outside_path")
def test_unannotated_value_naming_a_file_outside_the_root_passes(root: Path, fac: Fac) -> None:
    result = fac("page", cwd=root / "root")

    assert result.status == 0, result.err
    assert (root / "root" / "build" / "page.txt").read_text() == "../notes.txt"


@pytest.mark.project("str_list")
def test_value_annotated_str_may_name_a_file(root: Path, fac: Fac) -> None:
    result = fac("page")

    assert result.status == 0
    assert (root / "build" / "page.txt").read_text() == "notes.txt"


@pytest.mark.project("str_value")
def test_value_annotated_str_skips_the_path_check(root: Path, fac: Fac) -> None:
    result = fac("page")

    assert result.status == 0
    assert (root / "build" / "page.txt").read_text() == "notes.txt"


@pytest.mark.project("missing_source")
def test_missing_source_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'page' (build/page.html) inputs page.md, which doesn't exist, and no rule outputs it",
    ]


@pytest.mark.project("cycle")
def test_dependency_cycle_fails_printing_the_full_loop(fac: Fac) -> None:
    result = fac("first")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: dependency cycle: rule 'first' (build/a) -> rule 'third' (build/c) -> rule 'second' (build/b) -> rule 'first' (build/a)",
        "fac.py:4:2: note: rule 'first' (build/a) inputs build/c, which rule 'third' (build/c) outputs",
        "fac.py:14:2: note: rule 'third' (build/c) inputs build/b, which rule 'second' (build/b) outputs",
        "fac.py:9:2: note: rule 'second' (build/b) inputs build/a, which rule 'first' (build/a) outputs",
    ]


@pytest.mark.project("cycle_from_outside")
def test_dependency_cycle_reached_from_outside_names_only_its_members(fac: Fac) -> None:
    result = fac("entry")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:9:2: error: dependency cycle: rule 'first' (build/a) -> rule 'second' (build/b) -> rule 'first' (build/a)",
        "fac.py:9:2: note: rule 'first' (build/a) inputs build/b, which rule 'second' (build/b) outputs",
        "fac.py:14:2: note: rule 'second' (build/b) inputs build/a, which rule 'first' (build/a) outputs",
    ]


@pytest.mark.project("each_not_dict")
def test_each_item_that_is_not_a_dict_fails(fac: Fac) -> None:
    result = fac("touch")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: each= item 1 is a list, not a dict",
    ]


@pytest.mark.project("each_unknown_key")
def test_each_item_key_naming_no_parameter_fails(fac: Fac) -> None:
    result = fac("touch")

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:4:2: error: each= item 0 fills 'ouput', which names no parameter",
        "fac.py:4:2: error: parameter output has no value",
    ]


@pytest.mark.project("load_error")
def test_error_in_fac_py_prints_its_traceback_then_its_location(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines()[-1] == "fac.py:1:19: error: loading fac.py raised NameError"
    assert "NameError: name 'UNDEFINED' is not defined" in result.err
