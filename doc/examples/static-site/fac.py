"""A static site: one rule per page, an index of their titles, and a directory holding the result. It needs nothing but Python."""

import os
import shutil
import sys

from tools.render import fill_template, find_title, render_body

import facere as fac

fac.minimum_version("0.2")

SITE_NAME = "Facere example"
TEMPLATE = "template.html"
SOURCES = fac.sources("pages/*.md")
PAGE_RULES = [{"source": source, "html": fac.out(source, ".html")} for source in SOURCES]
PAGES = [rule["html"] for rule in PAGE_RULES]
INDEX = fac.out("pages/index.html")
SITE = fac.out("site")


@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output, template: fac.Input = TEMPLATE):
    markdown = fac.read_text(source)
    text = fill_template(
        fac.read_text(template), SITE_NAME, find_title(markdown), render_body(markdown)
    )
    fac.write_text(html, text)


@fac.rule
def index(
    sources: list[fac.Input] = SOURCES, template: fac.Input = TEMPLATE, html: fac.Output = INDEX
):
    items = ""
    for source in sources:
        href = os.path.basename(source).replace(".md", ".html")
        items += f'<li><a href="{href}">{find_title(fac.read_text(source))}</a></li>\n'
    text = fill_template(fac.read_text(template), SITE_NAME, "Pages", f"<ul>\n{items}</ul>")
    fac.write_text(html, text)


@fac.rule(default=True)
def site(pages: list[fac.Input] = PAGES, home: fac.Input = INDEX, folder: fac.Output = SITE):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    for html in pages + [home]:
        shutil.copy2(html, folder)


@fac.task
def serve(args: fac.Args, folder: fac.Input = SITE):
    """Serve the site, on the port after -- when one is given."""
    fac.run(sys.executable, "-m", "http.server", args, "--directory", folder)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
