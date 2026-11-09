"""A small website: each text file in pages/ becomes a page, with a home page and a sitemap. It needs nothing but Python."""

import os
import shutil
import sys
from pathlib import PurePosixPath

import facere as fac

# A constant joins the fingerprint of each rule that reads it, so a new name executes those rules.
SITE_NAME = "My site"
BASE_URL = "https://example.com/"
# An input of `page` and `index`, so editing it executes them all.
TEMPLATE = "template.html"
SITEMAP_TOOL = "tools/sitemap.py"
SERVER_TOOL = "tools/live_server.py"
# A new file in pages/ joins the build by existing.
SOURCES = fac.sources("pages/*.txt")
PAGE_RULES = [
    {"source": source, "html": fac.out(source, ".html"), "title": fac.out(f"titles/{source}")}
    for source in SOURCES
]
TITLES = [rule["title"] for rule in PAGE_RULES]
PAGE_NAMES = [PurePosixPath(source).stem + ".html" for source in SOURCES]
INDEX = fac.out("pages/index.html")
SITEMAP = fac.out("pages/sitemap.txt")
SITE = [rule["html"] for rule in PAGE_RULES] + [INDEX, SITEMAP]


# A recipe reaches this by name, so editing it executes every rule that calls it.
def fill(template, title, body):
    text = template.replace("{site}", SITE_NAME)
    return text.replace("{title}", title).replace("{body}", body)


# Edit a paragraph and this rule executes, but the title comes out the same, so `index` does not.
@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output, title: fac.Output, template: fac.Input = TEMPLATE):
    paragraphs = fac.read_text(source).strip().split("\n\n")
    body = ""
    for paragraph in paragraphs[1:]:
        body += f"<p>{paragraph}</p>\n"
    fac.write_text(title, paragraphs[0])
    fac.write_text(html, fill(fac.read_text(template), paragraphs[0], body))


# Inputs the titles and not the pages, so a page's new paragraph leaves it up to date.
@fac.rule
def index(
    titles: list[fac.Input] = TITLES, template: fac.Input = TEMPLATE, html: fac.Output = INDEX
):
    body = ""
    for title in titles:
        link = PurePosixPath(title).stem + ".html"
        body += f'<p><a href="{link}">{fac.read_text(title)}</a></p>\n'
    fac.write_text(html, fill(fac.read_text(template), "Home", body))


# The names are values, so a page's content can't make this stale, only a page added or removed.
# The script is an input, so editing it executes this rule alone.
@fac.rule
def sitemap(
    page_names: list[str] = PAGE_NAMES, tool: fac.Input = SITEMAP_TOOL, output: fac.Output = SITEMAP
):
    fac.run(sys.executable, tool, BASE_URL, "index.html", page_names, stdout=output)


# A task executes every time you ask, after the rules that output its inputs. While it runs, `fac` in
# another terminal rebuilds what an edit reached, and the server reloads each open page.
@fac.task
def serve(args: fac.Args, files: list[fac.Input] = SITE, tool: fac.Input = SERVER_TOOL):
    fac.run(sys.executable, tool, fac.out("pages"), args)


# Deleting build/ forgets every record, so the next `fac` executes every rule.
@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
