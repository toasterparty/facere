"""The my-site example, which getting started builds up to and which needs nothing but Python."""

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from ..helpers import EXAMPLES, REPO, closing_line, copy_example, edit, run_fac

GUIDE = REPO / "doc" / "user" / "1-getting-started.md"


def test_my_site_is_the_project_getting_started_finishes_with() -> None:
    listings = re.findall(r"^```python\n(.*?)^```", GUIDE.read_text(encoding="utf-8"), re.M | re.S)

    assert listings[-1] == (EXAMPLES / "my-site" / "fac.py").read_text(encoding="utf-8")


def test_a_site_rebuilds_only_what_a_change_reaches(tmp_path: Path) -> None:
    root = copy_example("my-site", tmp_path)
    pages = root / "pages"

    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules."
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 6 outputs up to date."

    (pages / "about.txt").touch()
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 6 outputs up to date."

    edit(pages / "about.txt", "building things", "making things")
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 4 outputs up to date."
    assert "<p>I like making things.</p>" in (root / "build/pages/about.html").read_text()

    edit(pages / "about.txt", "About me", "About")
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 3 outputs up to date."
    assert '<a href="about.html">About</a>' in (root / "build/pages/index.html").read_text()

    edit(root / "fac.py", "    body = ", "    # Starts empty.\n    body = ")
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 6 outputs up to date."

    edit(root / "fac.py", "<p>{paragraph}</p>", "<p class='text'>{paragraph}</p>")
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 2 outputs up to date."

    edit(root / "fac.py", '"My site"', '"Another name"')
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 1 output up to date."

    edit(root / "template.html", "<body>", "<body class='site'>")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 1 output up to date."

    edit(root / "tools" / "sitemap.py", "base_url + page", 'base_url + "/" + page')
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 5 outputs up to date."

    (pages / "contact.txt").write_text("Contact\n\nWrite to me.\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 4 outputs up to date."
    assert (
        (root / "build/pages/sitemap.txt").read_text().splitlines()[-1].endswith("/projects.html")
    )

    with (root / "build/pages/about.html").open("a") as page:
        page.write("edited by hand\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 6 outputs up to date."
    assert "edited by hand" not in (root / "build/pages/about.html").read_text()


def test_a_mistake_fails_before_any_recipe_and_a_new_build_starts_from_nothing(
    tmp_path: Path,
) -> None:
    root = copy_example("my-site", tmp_path)
    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules."

    (root / "template.html").rename(root / "moved.html")
    result = run_fac(root)
    assert result.status == 2
    assert "template.html" in result.err

    (root / "moved.html").rename(root / "template.html")
    assert closing_line(root, "clean") == "Finished in <elapsed>. Executed 1 task."
    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules."


def test_serve_adds_reloading_to_pages_and_reports_each_rebuild(tmp_path: Path) -> None:
    root = copy_example("my-site", tmp_path)
    localhost = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def fetch(url: str) -> str:
        with localhost.open(url) as response:
            body = response.read()
        assert isinstance(body, bytes)
        return body.decode()

    server = subprocess.Popen(
        [sys.executable, "-m", "facere", "serve", "--", "0"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    assert server.stdout is not None
    try:
        url = server.stdout.readline().split()[-1]
        version = fetch(f"{url}/__version")

        assert "<h1>About me</h1>" in fetch(f"{url}/about.html")
        assert version in fetch(f"{url}/about.html")
        assert "<h1>Home</h1>" in fetch(f"{url}/")
        assert fetch(f"{url}/sitemap.txt").startswith("https://example.com/index.html")
        assert "__version" not in (root / "build/pages/about.html").read_text()

        assert fetch(f"{url}/__version") == version

        edit(root / "pages" / "about.txt", "building things", "making things")
        assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 4 outputs up to date."

        assert fetch(f"{url}/__version") != version
        assert "making things" in fetch(f"{url}/about.html")
    finally:
        server.terminate()
        server.wait()
        server.stdout.close()
