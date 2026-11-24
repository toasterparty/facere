"""Stores and their virtual outputs, beyond what the many-rows and http-api examples show: what collection rejects, and how a store or a recipe that misbehaves fails the invocation."""

import json
import signal
import sys
from pathlib import Path

import pytest

from ..helpers import Fac, closing_line, edit, mask_elapsed, start_fac, wait_for

_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="these signals reach a process this way only on POSIX"
)


@pytest.mark.project("misdeclared")
def test_virtual_parameters_holding_what_their_annotation_rules_out_fail_collection(
    fac: Fac,
) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:21:2: error: parameter output is annotated fac.Output[fac.Virtual] but holds 'build/a.txt', not a fac.Virtual",
        "fac.py:26:2: error: parameter source is annotated fac.Input but holds fac.Virtual('about', store=Pages), not a path",
        "fac.py:31:2: error: parameter source is annotated fac.Input but holds the URI 's3://sales/2026.csv', not a path, and an input that is no file is a fac.Virtual",
        "fac.py:36:2: error: parameter output is annotated fac.Output[fac.Virtual] but holds the virtual source fac.Virtual('v1', fingerprint=len), which no rule writes, since Facere knows it only by its signature",
        "fac.py:41:2: error: task publish declares a fac.Input[fac.Virtual], which only a rule's record can track, since a task records nothing",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("unhashable")
def test_virtual_outputs_whose_store_or_key_facere_cannot_hash_fail_collection(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:47:2: error: parameter output holds a fac.Virtual whose store, of type __fac__.Locked, Facere can't hash, since pickle can't take it apart: cannot pickle '_thread.lock' object",
        "fac.py:52:2: error: parameter output holds a fac.Virtual whose store, of type __fac__.Unwritable, has no update method, though a store other than a FileStore has stamp, read, and update",
        "fac.py:57:2: error: parameter output holds a fac.Virtual whose key, of type list, can't be a dict's key",
        "fac.py:62:2: error: parameter output holds a fac.Virtual whose key, of type _thread.lock, Facere can't hash, since pickle can't take it apart: cannot pickle '_thread.lock' object",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("conflicts")
def test_virtual_outputs_claimed_twice_unwritten_or_overwritten_as_a_file_fail_collection(
    fac: Fac,
) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:16:2: error: 2 rules output build/table.txt[a]",
        "fac.py:16:2: note: rule 'first' (build/table.txt[a]) outputs build/table.txt[a]",
        "fac.py:21:2: note: rule 'second' (build/table.txt[a]) outputs build/table.txt[a]",
        "fac.py:26:2: error: rule 'reader' (build/listing.txt) inputs build/table.txt[z], which no rule outputs, though a store is never a source, and an input no rule writes is a fac.Virtual given fingerprint=",
        "fac.py:31:2: error: rule 'whole' (build/table.txt) outputs build/table.txt, which holds the virtual outputs of a FileStore",
        "fac.py:16:2: note: rule 'first' (build/table.txt[a]) declares a virtual output of it",
        "fac.py:16:2: error: 2 FileStore values share the path build/table.txt",
        "fac.py:16:2: note: rule 'first' (build/table.txt[a]) declares a virtual output of one",
        "fac.py:36:2: note: rule 'other' (build/table.txt[b]) declares a virtual output of one",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("virtual_cycle")
def test_rules_reading_each_others_virtual_outputs_fail_as_a_cycle(fac: Fac) -> None:
    result = fac()

    assert result.status == 2
    assert result.err.splitlines() == [
        "fac.py:17:2: error: dependency cycle: rule 'ping' (build/table.txt[a]) -> rule 'pong' (build/table.txt[b]) -> rule 'ping' (build/table.txt[a])",
        "fac.py:17:2: note: rule 'ping' (build/table.txt[a]) inputs build/table.txt[b], which rule 'pong' (build/table.txt[b]) outputs",
        "fac.py:22:2: note: rule 'pong' (build/table.txt[b]) inputs build/table.txt[a], which rule 'ping' (build/table.txt[a]) outputs",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("memo")
def test_a_store_whose_stamp_raises_fails_the_invocation_naming_the_store_and_method(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "raise-stamp").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: stamp refused",
        "fac.py:47:2: error: store Memo failed: its stamp raised RuntimeError",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("memo")
def test_a_store_whose_update_raises_leaves_its_rules_to_execute_again(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", '"alpha"', '"ALPHA"')
    (root / "raise-update").touch()

    failed = fac()
    (root / "raise-update").unlink()
    retried = fac()

    assert failed.status == 1
    assert failed.err.splitlines()[-3:] == [
        "RuntimeError: update refused",
        "fac.py:47:2: error: store Memo failed: its update raised RuntimeError",
        "Failed after <elapsed>. Executed 2 rules. 1 output up to date.",
    ]
    assert retried.err == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date.\n"
    assert json.loads((root / "memo.json").read_text()) == {"a": "ALPHA", "b": "beta"}


@pytest.mark.project("memo")
def test_a_read_that_disagrees_with_what_was_written_fails_the_round_trip(
    root: Path, fac: Fac
) -> None:
    (root / "garble-read").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines()[-2:] == [
        "fac.py:47:2: error: store Memo failed: its read returned note[a], which differs from what was written",
        "Failed after <elapsed>. Executed 3 rules.",
    ]


@pytest.mark.project("memo")
def test_an_update_that_disturbs_a_virtual_output_it_was_not_given_fails_the_round_trip(
    root: Path, fac: Fac
) -> None:
    fac()
    edit(root / "fac.py", '"alpha"', '"ALPHA"')
    (root / "drop-update").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:47:2: error: store Memo failed: its read found note[b] changed, though no rule wrote it",
        "Failed after <elapsed>. Executed 2 rules. 1 output up to date.",
    ]


@pytest.mark.project("memo")
def test_fac_read_of_a_value_not_in_memory_calls_the_store_unchecked_for_undeclared_paths(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "separator.txt").write_text(" & ")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date.\n"
    assert (root / "build" / "joined.txt").read_text() == "a=alpha & b=beta"


@pytest.mark.project("memo")
def test_a_store_method_that_changes_an_attribute_fails_the_invocation(
    root: Path, fac: Fac
) -> None:
    (root / "move-update").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:47:2: error: store Memo failed: its update changed an attribute of the store",
        "Failed after <elapsed>. Executed 3 rules.",
    ]


@pytest.mark.project("memo")
def test_a_recipe_succeeding_without_writing_its_virtual_output_fails(fac: Fac) -> None:
    result = fac("forgetful")

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:66:2: error: rule 'forgetful' (forgetful[c]) failed: its recipe succeeded without writing forgetful[c]",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("memo")
def test_fac_write_of_a_value_facere_cannot_hash_fails_the_recipe(fac: Fac) -> None:
    result = fac("unhashable_value")

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "TypeError: fac.write got a value of type _thread.lock, which Facere can't hash, since pickle can't take it apart: cannot pickle '_thread.lock' object",
        "fac.py:71:2: error: rule 'unhashable_value' (unhashable_value[d]) failed",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("memo")
def test_fac_read_of_a_virtual_output_the_rule_does_not_input_fails_the_recipe(fac: Fac) -> None:
    result = fac("undeclared")

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "ValueError: fac.read got fac.Virtual('a', store=Memo), which the rule declares as no fac.Input[fac.Virtual]",
        "fac.py:76:2: error: rule 'undeclared' (build/undeclared.txt) failed",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("memo")
def test_fac_read_in_a_task_fails_the_task(fac: Fac) -> None:
    result = fac("peek")

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: fac.read works only in the recipe of a rule, on the recipe's own thread, since a task records nothing",
        "fac.py:81:2: error: task 'peek' failed",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("table")
def test_a_file_store_whose_read_raises_holds_no_virtual_outputs(root: Path, fac: Fac) -> None:
    table = root / "build" / "table.txt"
    fac()
    table.write_text("torn")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert table.read_text() == "a=alpha\nb=beta\n"


@pytest.mark.project("table")
def test_a_file_store_keeps_the_rows_no_rule_declares_after_those_that_one_does(
    root: Path, fac: Fac
) -> None:
    table = root / "build" / "table.txt"
    fac()
    table.write_text("z=zeta\na=alpha\nb=beta\n")
    edit(root / "fac.py", '"alpha"', '"ALPHA"')

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 1 rule. 1 output up to date.\n"
    assert table.read_text() == "a=ALPHA\nb=beta\nz=zeta\n"


@pytest.mark.project("table")
def test_a_recipe_opening_a_file_store_it_writes_nothing_to_fails(fac: Fac) -> None:
    fac()

    result = fac("peek")

    assert result.status == 1
    assert result.err.splitlines()[-2:] == [
        "fac.py:30:2: error: rule 'peek' (build/peek.txt) failed: its recipe opened build/table.txt, which no fac.Input parameter declares",
        "Failed after <elapsed>.",
    ]


@pytest.mark.project("table")
def test_a_file_store_path_target_builds_every_rule_writing_to_it(fac: Fac) -> None:
    assert fac("build/table.txt").err == "Finished in <elapsed>. Executed 2 rules.\n"


@pytest.mark.project("table")
def test_a_virtual_output_target_builds_the_one_rule_writing_it(root: Path, fac: Fac) -> None:
    result = fac("build/table.txt[b]")

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "table.txt").read_text() == "b=beta\n"


@pytest.mark.project("table")
def test_a_rule_inputting_a_file_store_path_reads_every_value_written_to_it(
    root: Path, fac: Fac
) -> None:
    built = fac("shout")
    current = fac("shout")
    edit(root / "fac.py", '"alpha"', '"ALPHA!"')
    edited = fac("shout")

    assert built.err == "Finished in <elapsed>. Executed 3 rules.\n"
    assert current.err == "Finished in <elapsed>. No work to do. 3 outputs up to date.\n"
    assert edited.err == "Finished in <elapsed>. Executed 2 rules. 1 output up to date.\n"
    assert (root / "build" / "shout.txt").read_text() == "A=ALPHA!\nB=BETA\n"


@pytest.mark.project("table")
def test_a_path_target_ending_in_brackets_builds_the_rule_outputting_that_path(
    root: Path, fac: Fac
) -> None:
    result = fac("build/app/[slug]")

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert (root / "build" / "app" / "[slug]").read_text() == "slug"


@pytest.mark.project("odd")
def test_keep_going_executes_no_task_after_a_store_failed_to_take_its_rules_values(
    root: Path, fac: Fac
) -> None:
    (root / "raise-update").touch()

    result = fac("-k", "publish")

    assert result.status == 1
    assert result.out == ""
    assert result.err.splitlines()[-3:] == [
        "RuntimeError: update refused",
        "fac.py:42:2: error: store Odd failed: its update raised RuntimeError",
        "Failed after <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("odd")
def test_a_store_whose_read_returns_no_mapping_fails_the_invocation(root: Path, fac: Fac) -> None:
    (root / "list-read").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:42:2: error: store Odd failed: its read returned a list, not a mapping",
        "Failed after <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("odd")
def test_a_store_whose_read_returns_a_value_facere_cannot_hash_fails_the_invocation(
    root: Path, fac: Fac
) -> None:
    (root / "lock-read").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:42:2: error: store Odd failed: its read returned pair[a] as a value of type _thread.lock, which Facere can't hash, since pickle can't take it apart: cannot pickle '_thread.lock' object",
        "Failed after <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("odd")
def test_a_read_leaving_out_what_was_written_fails_the_round_trip(root: Path, fac: Fac) -> None:
    (root / "empty-read").touch()

    result = fac()

    assert result.status == 1
    assert result.err.splitlines() == [
        "fac.py:42:2: error: store Odd failed: its read left out pair[a], which was written",
        "Failed after <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("odd")
def test_a_rule_whose_one_store_fails_keeps_the_other_store_written_and_executes_again(
    root: Path, fac: Fac
) -> None:
    # The stamp fails after the update, so the failing store holds the value too.
    (root / "lock-stamp").touch()

    failed = fac()
    table = (root / "build" / "table.txt").read_text()
    (root / "lock-stamp").unlink()
    retried = fac()

    assert failed.status == 1
    assert failed.err.splitlines() == [
        "fac.py:42:2: error: store Odd failed: its stamp returned a value of type _thread.lock, which Facere can't hash, since pickle can't take it apart: cannot pickle '_thread.lock' object",
        "Failed after <elapsed>. Executed 1 rule.",
    ]
    assert table == "a=alpha\n"
    assert retried.err == "Finished in <elapsed>. Executed 1 rule.\n"


def _read_calls(root: Path) -> list[str]:
    """Return the virtual sources the sources fixture's signature function was called for, in sorted order, since calls run concurrently."""
    calls = root / "calls.txt"
    return sorted(calls.read_text().splitlines()) if calls.exists() else []


@pytest.mark.project("sources")
def test_a_signature_is_called_once_per_invocation_however_many_rules_input_its_source(
    root: Path, fac: Fac
) -> None:
    built = fac()
    built_calls = _read_calls(root)
    current = fac()

    assert built.err == "Finished in <elapsed>. Executed 4 rules.\n"
    assert built_calls == ["cc", "ld"]
    assert current.err == "Finished in <elapsed>. No work to do. 4 outputs up to date.\n"
    assert _read_calls(root) == ["cc", "cc", "ld", "ld"]


@pytest.mark.project("sources")
def test_a_recipe_reaches_the_key_of_the_virtual_source_it_inputs(root: Path, fac: Fac) -> None:
    fac("link")

    assert (root / "build" / "app").read_text() == "linked by ld"


@pytest.mark.project("sources")
def test_no_signature_is_called_for_targets_whose_rules_input_no_virtual_source(
    root: Path, fac: Fac
) -> None:
    result = fac("readme")

    assert result.err == "Finished in <elapsed>. Executed 1 rule.\n"
    assert _read_calls(root) == []


@pytest.mark.project("sources")
def test_a_changed_signature_executes_again_exactly_the_rules_inputting_its_source(
    root: Path, fac: Fac
) -> None:
    fac()
    (root / "cc.version").write_text("2\n")

    result = fac()

    assert result.err == "Finished in <elapsed>. Executed 3 rules. 1 output up to date.\n"


@pytest.mark.project("sources")
def test_a_signature_that_raises_fails_every_rule_inputting_its_source(
    root: Path, fac: Fac
) -> None:
    (root / "cc.version").unlink()

    result = fac("-k", "-j", "1")

    assert result.status == 1
    assert result.err.splitlines()[-5:] == [
        "FileNotFoundError: [Errno 2] No such file or directory: 'cc.version'",
        "fac.py:23:2: error: rule 'compile' (build/a.o) failed: the signature of its input cc raised FileNotFoundError",
        "fac.py:23:2: error: rule 'compile' (build/b.o) failed: the signature of its input cc raised FileNotFoundError",
        "fac.py:23:2: error: rule 'compile' (build/c.o) failed: the signature of its input cc raised FileNotFoundError",
        "Failed after <elapsed>. Executed 1 rule.",
    ]


@pytest.mark.project("sources")
def test_fac_read_of_a_virtual_source_fails_the_recipe(fac: Fac) -> None:
    result = fac("misread")

    assert result.status == 1
    assert result.err.splitlines()[-3:] == [
        "ValueError: fac.read got the virtual source fac.Virtual('cc', fingerprint=version), whose content Facere knows only by its signature",
        "fac.py:40:2: error: rule 'misread' (build/misread.txt) failed",
        "Failed after <elapsed>.",
    ]


@_POSIX_ONLY
@pytest.mark.project("stop")
def test_interrupt_writes_nothing_to_a_store_and_leaves_its_rules_to_execute_again(
    root: Path,
) -> None:
    process = start_fac(root)
    wait_for(root / "build" / "started")

    process.send_signal(signal.SIGINT)
    (root / "go").touch()
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 130, stderr
    assert mask_elapsed(stderr) == (
        "fac.py:31:2: note: interrupted rule 'slow' (build/listing.txt)\n"
        "Interrupted after <elapsed>. Executed 1 rule.\n"
    )
    assert not (root / "build" / "table.txt").exists()
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules."


@_POSIX_ONLY
@pytest.mark.project("stop")
def test_graceful_stop_writes_what_the_rules_that_finished_set(root: Path) -> None:
    process = start_fac(root)
    wait_for(root / "build" / "started")

    process.send_signal(signal.SIGTERM)
    (root / "go").touch()
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 143, stderr
    assert mask_elapsed(stderr) == "Stopped after <elapsed>. Executed 2 rules.\n"
    assert (root / "build" / "table.txt").read_text() == "a=alpha\n"
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date."
