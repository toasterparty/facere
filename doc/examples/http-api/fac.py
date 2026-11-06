"""Pages rendered from local Markdown, each published to a CMS's HTTP REST API, with a local list of titles built from what was published."""

import html
import json
import os
import re
import shutil
import urllib.request
from pathlib import PurePosixPath

import facere as fac

CMS_URL = "http://127.0.0.1:8000/pages"
TITLE = re.compile(r"<h1>(.*)</h1>")


class Pages:
    """A CMS's pages, keyed by slug, each one HTML document."""

    def __init__(self, url):
        self.url = url

    def stamp(self):
        with urllib.request.urlopen(urllib.request.Request(self.url, method="HEAD")) as response:
            return response.headers["ETag"]

    def read(self, keys):
        with urllib.request.urlopen(self.url) as response:
            return json.load(response)

    def update(self, changed):
        for slug, page in changed.items():
            request = urllib.request.Request(f"{self.url}/{slug}", page.encode(), method="PUT")
            urllib.request.urlopen(request).close()


CMS = Pages(CMS_URL)
SOURCES = fac.sources("pages/*.md")
PREVIEW_RULES = [{"source": source, "rendered": fac.out(source, ".html")} for source in SOURCES]
PAGE_RULES = [
    {"rendered": rule["rendered"], "output": fac.Virtual(CMS, PurePosixPath(rule["source"]).stem)}
    for rule in PREVIEW_RULES
]


def render(markdown):
    blocks = markdown.split("\n\n")
    rendered = [f"<h1>{html.escape(blocks[0].removeprefix('# '))}</h1>"]
    for text in blocks[1:]:
        if text.strip():
            rendered.append(f"<p>{html.escape(' '.join(text.split()))}</p>")
    return "\n".join(rendered) + "\n"


@fac.rule(each=PREVIEW_RULES)
def preview(source: fac.Input, rendered: fac.Output):
    fac.write_text(rendered, render(fac.read_text(source)))


@fac.rule(each=PAGE_RULES, default=True)
def page(rendered: fac.Input, output: fac.VirtualOutput):
    fac.write(output, fac.read_text(rendered))


@fac.rule(default=True)
def titles(
    pages: list[fac.VirtualInput] = [rule["output"] for rule in PAGE_RULES],
    listing: fac.Output = fac.out("titles.txt"),
):
    lines = []
    for page in pages:
        title = TITLE.search(fac.read(page))
        assert title, f"page {page.key} has no <h1>"
        lines.append(f"{page.key}: {title.group(1)}\n")
    fac.write_text(listing, "".join(lines))


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
