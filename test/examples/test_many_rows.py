"""The many-rows example, which needs only Python."""

import shutil
from pathlib import Path

import pytest

from ..helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "doc" / "examples" / "many-rows"

pytestmark = pytest.mark.skip(reason="planned: stores are in no release yet")


def _copy_example(tmp_path: Path) -> Path:
    root = tmp_path / "many-rows"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "table.txt"))
    edit(root / "fac.py", "ROW_COUNT = 1500", "ROW_COUNT = 100")
    return root


def test_many_rows_rewrites_exactly_the_rows_the_table_changed(tmp_path: Path) -> None:
    root = _copy_example(tmp_path)
    rows = root / "build" / "rows.txt"

    first = run_fac(root)
    written_ns = rows.stat().st_mtime_ns
    second = run_fac(root)
    unwritten_ns = rows.stat().st_mtime_ns
    invalidated = run_fac(root, "invalidate", "--", "--count", "25")
    third = run_fac(root)
    edit(rows, "0007 revision 1\n", "0007 revision 9\n")
    hand_edited = run_fac(root)
    rows.unlink()
    deleted = run_fac(root)

    assert first.err == "Finished in <elapsed>. Executed 100 rules.\n"
    assert second.err == "Finished in <elapsed>. No work to do. 100 outputs up to date.\n"
    assert unwritten_ns == written_ns
    assert invalidated.status == 0, invalidated.err
    assert third.err == "Finished in <elapsed>. Executed 25 rules. 75 outputs up to date.\n"
    assert hand_edited.err == "Finished in <elapsed>. Executed 1 rule. 99 outputs up to date.\n"
    assert deleted.err == "Finished in <elapsed>. Executed 100 rules.\n"
    lines = rows.read_text().splitlines()
    assert len(lines) == 100
    assert lines[:2] == ["0000 revision 1", "0001 revision 1"]
    assert lines[7] == "0007 revision 1"
    assert lines[24:26] == ["0024 revision 1", "0025 revision 0"]


def test_many_rows_reruns_every_row_when_the_store_changes_and_none_when_a_task_does(
    tmp_path: Path,
) -> None:
    root = _copy_example(tmp_path)

    first = run_fac(root)
    edit(root / "fac.py", 'prog="fac invalidate --"', 'prog="invalidate"')
    task_edited = run_fac(root)
    edit(root / "fac.py", 'f"{row:04d} {text}\\n"', 'f"{row:05d} {text}\\n"')
    store_edited = run_fac(root)

    assert first.err == "Finished in <elapsed>. Executed 100 rules.\n"
    assert task_edited.err == "Finished in <elapsed>. No work to do. 100 outputs up to date.\n"
    assert store_edited.err == "Finished in <elapsed>. Executed 100 rules.\n"
    assert (root / "build" / "rows.txt").read_text().splitlines()[0] == "00000 revision 0"
