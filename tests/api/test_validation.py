"""Collection errors: each fails before any recipe executes, in GNU format, naming every definition involved and how to fix it."""

from pathlib import Path

import pytest

from tests.helpers import Fac


@pytest.mark.project("case_clash")
def test_two_rules_outputting_one_path_compared_without_case_fail(root: Path, fac: Fac) -> None:
    result = fac("lower")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: 2 outputs claim build/x.txt, compared without case: give each rule outputs of its own",
        "fac.py:4:2: note: rule 'lower' (build/x.txt) outputs build/x.txt",
        "fac.py:9:2: note: rule 'upper' (build/X.txt) outputs build/X.txt",
    ]
    assert not (root / "build" / "x.txt").exists()


@pytest.mark.project("rule_without_output")
def test_rule_without_output_fails(fac: Fac) -> None:
    result = fac("nothing")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule nothing declares no output: annotate the parameter its recipe writes fac.Output, or make it a task with @fac.task",
    ]


@pytest.mark.project("task_with_output")
def test_task_with_output_fails(fac: Fac) -> None:
    result = fac("report")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: task report declares an output, but a task writes no tracked output: make it a rule with @fac.rule, or drop the fac.Output annotation",
    ]


@pytest.mark.project("star_parameters")
def test_rule_taking_star_args_or_star_star_kwargs_fails(fac: Fac) -> None:
    result = fac("positional")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: positional takes *paths, which no rule or task can fill: name each parameter",
        "fac.py:9:2: error: keyword takes **options, which no rule or task can fill: name each parameter",
    ]


@pytest.mark.project("not_a_path")
def test_path_parameter_holding_no_path_fails_naming_its_annotation(fac: Fac) -> None:
    result = fac("copy")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: parameter source is annotated fac.Input but holds '': pass a path, strings with /",
        "fac.py:9:2: error: parameter pages is annotated list[fac.Input] but holds 'a.md': pass a list of paths, strings with /",
    ]


@pytest.mark.project("unreadable_annotation")
def test_annotation_facere_cannot_read_fails(fac: Fac) -> None:
    result = fac("optional")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:6:2: error: parameter source has an annotation Facere can't read: annotate it fac.Input, list[fac.Input], fac.Output, or list[fac.Output]",
        "fac.py:11:2: error: can't read the annotations of undefined: NameError: name 'Missing' is not defined",
    ]


@pytest.mark.project("state_output")
def test_output_holding_the_state_fails(fac: Fac) -> None:
    result = fac("everything")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'everything' (build) outputs build, which holds Facere's state: output a path inside the output directory instead",
        "fac.py:9:2: error: rule 'inside' (build/.fac/a) outputs build/.fac/a, which holds Facere's state: output a path inside the output directory instead",
    ]


@pytest.mark.project("shared_function_name")
def test_two_functions_sharing_a_name_fail(fac: Fac) -> None:
    result = fac("docs")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: 2 definitions share the name docs: rename all but one, with name= or def",
        "fac.py:4:2: note: rule 'docs' (build/a) is defined here",
        "fac.py:9:2: note: rule 'docs' (build/b) is defined here",
    ]


@pytest.mark.project("shared_task_name")
def test_two_tasks_sharing_a_name_fail(fac: Fac) -> None:
    result = fac("greet")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:8:1: error: 2 definitions share the name greet: rename all but one, with name= or def",
        "fac.py:8:1: note: task 'greet' is defined here",
        "fac.py:9:1: note: task 'greet' is defined here",
    ]


@pytest.mark.project("no_value")
def test_parameter_without_value_fails(fac: Fac) -> None:
    result = fac("copy")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: parameter source has no value: give it a default, or pass it through each= or a keyword argument",
    ]


@pytest.mark.project("option_name")
def test_parameter_named_after_an_option_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: parameter always is named after a fac.rule option, so no keyword argument can fill it: rename it",
    ]


@pytest.mark.project("unhashable")
def test_value_facere_cannot_hash_fails_naming_its_type(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:6:2: error: function page reads global LOCK, of type object, which Facere can't hash: pass None, a bool, int, float, str, bytes, module, function, or class, or a tuple, list, dict, or set of them",
        "fac.py:6:2: error: rule 'page' (build/a) reads parameter lock, of type object, which Facere can't hash: pass None, a bool, int, float, str, bytes, module, function, or class, or a tuple, list, dict, or set of them",
    ]


@pytest.mark.project("pure_path")
def test_pathlib_path_value_fails_suggesting_as_posix(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:6:2: error: rule 'page' (build/a) reads parameter directory, of type pathlib.PurePosixPath, which Facere can't hash: write path.as_posix(), since Facere paths are strings with /",
    ]


@pytest.mark.project("unannotated_file")
def test_unannotated_value_naming_a_file_under_the_root_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'page' (build/a) reads parameter source, which names the path notes.txt unannotated: annotate it fac.Input or list[fac.Input], or str or list[str] if its recipe never reads the file",
    ]


@pytest.mark.project("unannotated_output")
def test_unannotated_value_naming_a_path_a_rule_outputs_fails(fac: Fac) -> None:
    result = fac("index")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:9:2: error: rule 'index' (build/index.html) reads parameter pages, which names the path build/page.html unannotated: annotate it fac.Input or list[fac.Input], or str or list[str] if its recipe never reads the file",
    ]


@pytest.mark.project("global_path")
def test_global_naming_a_file_under_the_root_fails(fac: Fac) -> None:
    result = fac("page")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:6:2: error: function page reads global NOTES, which names the path notes.txt: pass the path through a parameter annotated fac.Input or list[fac.Input]",
    ]


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

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: rule 'page' (build/page.html) inputs page.md, which doesn't exist, and no rule outputs it: create it, fix the path, or define the rule that outputs it",
    ]


@pytest.mark.project("cycle")
def test_dependency_cycle_fails_printing_the_full_loop(fac: Fac) -> None:
    result = fac("first")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: dependency cycle: rule 'first' (build/a) -> rule 'third' (build/c) -> rule 'second' (build/b) -> rule 'first' (build/a): remove one of these inputs to break the loop",
        "fac.py:4:2: note: rule 'first' (build/a) inputs build/c, which rule 'third' (build/c) outputs",
        "fac.py:14:2: note: rule 'third' (build/c) inputs build/b, which rule 'second' (build/b) outputs",
        "fac.py:9:2: note: rule 'second' (build/b) inputs build/a, which rule 'first' (build/a) outputs",
    ]


@pytest.mark.project("cycle_from_outside")
def test_dependency_cycle_reached_from_outside_names_only_its_members(fac: Fac) -> None:
    result = fac("entry")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:9:2: error: dependency cycle: rule 'first' (build/a) -> rule 'second' (build/b) -> rule 'first' (build/a): remove one of these inputs to break the loop",
        "fac.py:9:2: note: rule 'first' (build/a) inputs build/b, which rule 'second' (build/b) outputs",
        "fac.py:14:2: note: rule 'second' (build/b) inputs build/a, which rule 'first' (build/a) outputs",
    ]


@pytest.mark.project("each_not_tuple")
def test_each_item_that_is_not_a_tuple_fails(fac: Fac) -> None:
    result = fac("touch")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:4:2: error: each= item 1 is a list, not a tuple: write each item as a tuple, such as (source, output)",
    ]


@pytest.mark.project("load_error")
def test_error_in_fac_py_prints_its_traceback_then_its_location(fac: Fac) -> None:
    result = fac()

    assert result.status == 1
    assert (
        result.err.splitlines()[-1]
        == "fac.py:1:19: error: loading fac.py raised NameError: fix the code the traceback above names"
    )
    assert "NameError: name 'UNDEFINED' is not defined" in result.err
