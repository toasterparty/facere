"""The static-site example, which needs nothing but Python."""

import shutil
from pathlib import Path

from ..helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "doc" / "examples" / "static-site"


def test_a_site_rebuilds_only_the_pages_a_change_reaches(tmp_path: Path) -> None:
    root = tmp_path / "static-site"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build"))

    def closing_line(*args: str) -> str:
        result = run_fac(root, *args)
        assert result.status == 0, result.err
        return result.err.splitlines()[-1]

    assert closing_line() == "Finished in <elapsed>. Executed 4 rules."
    assert closing_line() == "Finished in <elapsed>. No work to do. 4 outputs up to date."

    edit(root / "pages" / "about.md", "built by Facere", "made by Facere")
    assert closing_line() == "Finished in <elapsed>. Executed 3 rules. 1 output up to date."
    assert "made by Facere" in (root / "build" / "site" / "about.html").read_text()

    edit(root / "tools" / "render.py", "def find_title", "# The first line.\ndef find_title")
    assert closing_line() == "Finished in <elapsed>. No work to do. 4 outputs up to date."

    edit(root / "tools" / "render.py", "<p>", "<p class='text'>")
    assert closing_line() == "Finished in <elapsed>. Executed 3 rules. 1 output up to date."

    edit(root / "fac.py", '"Facere example"', '"Another name"')
    assert closing_line() == "Finished in <elapsed>. Executed 4 rules."

    (root / "pages" / "news.md").write_text("# News\n\nNothing yet.\n")
    assert closing_line() == "Finished in <elapsed>. Executed 3 rules. 2 outputs up to date."
    assert (root / "build" / "site" / "news.html").exists()

    shutil.rmtree(root / "build" / "site")
    assert closing_line() == "Finished in <elapsed>. Executed 1 rule. 4 outputs up to date."
