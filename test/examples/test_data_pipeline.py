"""The data-pipeline example, which needs nothing but Python."""

from pathlib import Path

from ..helpers import closing_line, copy_example, edit, run_fac


def test_a_pipeline_stops_where_an_output_comes_out_the_same(tmp_path: Path) -> None:
    root = copy_example("data-pipeline", tmp_path)

    def add_row(path: Path, row: str) -> None:
        with path.open("a") as table:
            table.write(row)

    assert closing_line(root) == "Finished in <elapsed>. Executed 5 rules."
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 8 outputs up to date."

    add_row(root / "data" / "south.csv", "gears,5\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules. 2 outputs up to date."

    add_row(root / "data" / "north.csv", "gears,many\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 6 outputs up to date."
    assert (root / "build" / "data" / "north.rejects.txt").read_text() == "gears,many\n"

    edit(root / "fac.py", '"USD"', '"EUR"')
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 4 outputs up to date."

    edit(root / "fac.py", '"Sales by item"', '"Sales"')
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 6 outputs up to date."

    shown = run_fac(root, "show")
    assert (
        shown.out
        == "Sales\n\ngears          85\nsprockets      45\nwidgets       150\n\nTotal: 280 EUR\n"
    )
