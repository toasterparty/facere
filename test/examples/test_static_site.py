"""The static-site example, which needs nothing but Python."""

import shutil
from pathlib import Path

from ..helpers import closing_line, copy_example, edit, run_fac


def test_a_site_rebuilds_only_the_pages_a_change_reaches(tmp_path: Path) -> None:
    root = copy_example("static-site", tmp_path)

    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules."
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 4 outputs up to date."

    edit(root / "pages" / "about.md", "built by Facere", "made by Facere")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 1 output up to date."
    assert "made by Facere" in (root / "build" / "site" / "about.html").read_text()

    edit(root / "tools" / "render.py", "def find_title", "# The first line.\ndef find_title")
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 4 outputs up to date."

    edit(root / "tools" / "render.py", "<p>", "<p class='text'>")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 1 output up to date."

    edit(root / "fac.py", '"Facere example"', '"Another name"')
    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules."

    (root / "pages" / "news.md").write_text("# News\n\nNothing yet.\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 2 outputs up to date."
    assert (root / "build" / "site" / "news.html").exists()

    shutil.rmtree(root / "build" / "site")
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 4 outputs up to date."


def test_a_project_needing_a_newer_facere_fails_before_any_recipe(tmp_path: Path) -> None:
    root = copy_example("static-site", tmp_path)
    edit(root / "fac.py", 'fac.minimum_version("0.2")', 'fac.minimum_version("99.0")')

    result = run_fac(root)

    assert result.status == 2
    assert "uv tool upgrade facere" in result.err
    assert not (root / "build" / "site").exists()
