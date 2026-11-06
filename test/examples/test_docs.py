"""The user docs read in filename order, each page linking to its neighbors, and no relative link dangles."""

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_USER = _REPO / "doc" / "user"
_LINK = re.compile(r"\]\((\.{1,2}/[^)#]*)(?:#([^)]*))?\)")
_NAV = re.compile(r"\[[^\]]*\]\(\./([^)]+)\)")


def _heading_anchor(heading: str) -> str:
    text = heading.lower().replace("`", "").replace("*", "")
    return re.sub(r"[^a-z0-9 -]", "", text).strip().replace(" ", "-")


def test_each_page_ends_linking_to_the_pages_before_and_after_it() -> None:
    numbered = sorted(path.name for path in _USER.glob("[0-9]-*.md"))
    order = ["README.md", *numbered]

    for index, name in enumerate(order):
        last_line = (_USER / name).read_text(encoding="utf-8").splitlines()[-1]
        expected = order[max(index - 1, 0) : index] + order[index + 1 : index + 2]
        assert _NAV.findall(last_line) == expected, name


def test_every_page_is_numbered_but_the_readme() -> None:
    names = {path.name for path in _USER.glob("*.md")}

    assert {name for name in names if not re.match(r"\d-", name)} == {"README.md"}


@pytest.mark.parametrize("tree", ["doc/user", "doc/maintainer", "doc/examples"])
def test_relative_markdown_links_reach_a_file_and_its_heading(tree: str) -> None:
    broken = []
    for page in (_REPO / tree).glob("**/*.md"):
        for target, anchor in _LINK.findall(page.read_text(encoding="utf-8")):
            path = page.parent / target
            if not path.exists():
                broken.append(f"{page.relative_to(_REPO)}: {target}")
            elif anchor and path.suffix == ".md":
                headings = re.findall(r"^#+ (.*)$", path.read_text(encoding="utf-8"), re.M)
                if anchor not in {_heading_anchor(heading) for heading in headings}:
                    broken.append(f"{page.relative_to(_REPO)}: {target}#{anchor}")

    assert broken == []
