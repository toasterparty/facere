"""The data-pipeline example, which needs nothing but Python."""

import shutil
from pathlib import Path

from ..helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "doc" / "examples" / "data-pipeline"


def test_a_pipeline_stops_where_an_output_comes_out_the_same(tmp_path: Path) -> None:
    root = tmp_path / "data-pipeline"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build"))

    def closing_line(*args: str) -> str:
        result = run_fac(root, *args)
        assert result.status == 0, result.err
        return result.err.splitlines()[-1]

    def add_row(path: Path, row: str) -> None:
        with path.open("a") as table:
            table.write(row)

    assert closing_line() == "Finished in <elapsed>. Executed 5 rules."
    assert closing_line() == "Finished in <elapsed>. No work to do. 8 outputs up to date."

    add_row(root / "data" / "south.csv", "gears,5\n")
    assert closing_line() == "Finished in <elapsed>. Executed 4 rules. 2 outputs up to date."

    add_row(root / "data" / "north.csv", "gears,many\n")
    assert closing_line() == "Finished in <elapsed>. Executed 1 rule. 6 outputs up to date."
    assert (root / "build" / "data" / "north.rejects.txt").read_text() == "gears,many\n"

    edit(root / "fac.py", '"USD"', '"EUR"')
    assert closing_line() == "Finished in <elapsed>. Executed 3 rules. 4 outputs up to date."

    edit(root / "fac.py", '"Sales by item"', '"Sales"')
    assert closing_line() == "Finished in <elapsed>. Executed 2 rules. 6 outputs up to date."

    shown = run_fac(root, "show")
    assert (
        shown.out
        == "Sales\n\ngears          85\nsprockets      45\nwidgets       150\n\nTotal: 280 EUR\n"
    )
