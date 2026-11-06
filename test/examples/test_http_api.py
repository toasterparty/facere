"""The http-api example, publishing to the fake CMS in its `tools/`, served from this process on a free port."""

import importlib.util
import shutil
import threading
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

import pytest

from ..helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "doc" / "examples" / "http-api"

pytestmark = pytest.mark.skip(reason="planned: stores are in no release yet")


class _Cms(Protocol):
    requests: list[str]
    pages: dict[str, str]
    url: str

    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...


@pytest.fixture
def cms() -> Iterator[_Cms]:
    """Yield a running `FakeCms`, whose `requests` the test clears before each run it inspects."""
    spec = importlib.util.spec_from_file_location("fake_cms", EXAMPLE / "tools" / "fake_cms.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.FakeCms(port=0) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        yield cast("_Cms", server)
        server.shutdown()
        thread.join()


@pytest.fixture
def example(tmp_path: Path, cms: _Cms) -> Path:
    root = tmp_path / "http-api"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "__pycache__"))
    edit(root / "fac.py", '"http://127.0.0.1:8000/pages"', f'"{cms.url}"')
    return root


def _pop_requests(cms: _Cms) -> list[str]:
    requests = list(cms.requests)
    cms.requests.clear()
    return requests


def _pop_puts(cms: _Cms) -> list[str]:
    return [request for request in _pop_requests(cms) if request.startswith("PUT ")]


def test_http_api_publishes_exactly_the_pages_that_changed(example: Path, cms: _Cms) -> None:
    first = run_fac(example)
    first_puts = _pop_puts(cms)
    second = run_fac(example)
    second_requests = _pop_requests(cms)
    previews = run_fac(example, "preview")
    previews_requests = _pop_requests(cms)
    edit(example / "pages" / "about.md", "is built from", "is rendered from")
    edited = run_fac(example)
    edited_puts = _pop_puts(cms)
    defacing = urllib.request.Request(f"{cms.url}/about", b"<h1>Defaced</h1>\n", method="PUT")
    urllib.request.urlopen(defacing).close()
    cms.requests.clear()
    restored = run_fac(example)
    restored_puts = _pop_puts(cms)

    assert first.err == "Finished in <elapsed>. Executed 7 rules.\n"
    assert first_puts == ["PUT /pages/about", "PUT /pages/contact", "PUT /pages/index"]
    assert second.err == "Finished in <elapsed>. No work to do. 7 outputs up to date.\n"
    assert second_requests == ["HEAD /pages"]
    assert previews.err == "Finished in <elapsed>. No work to do. 3 outputs up to date.\n"
    assert previews_requests == []
    assert edited.err == "Finished in <elapsed>. Executed 3 rules. 4 outputs up to date.\n"
    assert edited_puts == ["PUT /pages/about"]
    assert restored.err == "Finished in <elapsed>. Executed 1 rule. 6 outputs up to date.\n"
    assert restored_puts == ["PUT /pages/about"]
    assert cms.pages["about"] == (
        "<h1>About</h1>\n<p>This site is rendered from Markdown by Facere and published to a CMS.</p>\n"
    )
    assert (example / "build" / "titles.txt").read_text() == (
        "about: About\ncontact: Contact\nindex: Welcome\n"
    )


def test_http_api_publishes_one_page_named_by_its_member(example: Path, cms: _Cms) -> None:
    first = run_fac(example)
    edit(example / "pages" / "about.md", "is built from", "is rendered from")
    edit(example / "pages" / "contact.md", "Write to", "Send mail to")
    cms.requests.clear()
    about = run_fac(example, "page[about]")
    about_puts = _pop_puts(cms)

    assert first.err == "Finished in <elapsed>. Executed 7 rules.\n"
    assert about.err == "Finished in <elapsed>. Executed 2 rules.\n"
    assert about_puts == ["PUT /pages/about"]


def test_http_api_builds_local_files_but_fails_publishing_while_the_cms_is_down(
    example: Path, cms: _Cms
) -> None:
    first = run_fac(example)
    cms.shutdown()
    cms.server_close()
    previews = run_fac(example, "preview")
    published = run_fac(example)

    assert first.err == "Finished in <elapsed>. Executed 7 rules.\n"
    assert previews.err == "Finished in <elapsed>. No work to do. 3 outputs up to date.\n"
    assert published.status == 1
