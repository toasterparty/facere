"""The many-files example, which needs only Python."""

import shutil
from pathlib import Path

from ..helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "doc" / "examples" / "many-files"


def test_many_files_rebuilds_exactly_the_rows_the_table_changed(tmp_path: Path) -> None:
    root = tmp_path / "many-files"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "table.txt"))
    edit(root / "fac.py", "ROW_COUNT = 1500", "ROW_COUNT = 100")

    first = run_fac(root)
    second = run_fac(root)
    invalidated = run_fac(root, "invalidate", "--", "--count", "25")
    third = run_fac(root)
    cleaned = run_fac(root, "clean")
    fourth = run_fac(root)
    (root / "build" / "rows" / "0007.txt").unlink()
    deleted = run_fac(root)

    assert first.err == "Finished in <elapsed>. Executed 100 rules.\n"
    assert second.err == "Finished in <elapsed>. No work to do. 100 outputs up to date.\n"
    assert invalidated.status == 0, invalidated.err
    assert third.err == "Finished in <elapsed>. Executed 25 rules. 75 outputs up to date.\n"
    assert cleaned.status == 0, cleaned.err
    assert fourth.err == "Finished in <elapsed>. Executed 100 rules.\n"
    assert deleted.err == "Finished in <elapsed>. Executed 1 rule. 99 outputs up to date.\n"
    assert (root / "build" / "rows" / "0000.txt").read_text() == "revision 1\n"
    assert (root / "build" / "rows" / "0025.txt").read_text() == "revision 0\n"
