# Getting started

Install Facere on Python 3.11 or newer with `uv tool install facere` or `pipx install facere`, which install it in an environment of its own and put the `fac` command on your `PATH`. Check that it runs:

```
$ fac --version
0.3.1
```

A project's rules live in a file named `fac.py` in its top directory, the root. The steps below grow one `fac.py` that builds a small website from text files, with nothing to install beyond Facere.

## Build one page: `about.txt` -> `about.html`

Put a title, then paragraphs, each separated by a blank line, in `pages/about.txt`:

```
About me

I like building things.
```

Put this in `fac.py`, beside `pages/`:

```python
import facere as fac


@fac.rule
def about(source: fac.Input = "pages/about.txt", html: fac.Output = fac.out("about.html")):
    fac.write_text(html, f"<pre>{fac.read_text(source)}</pre>\n")
```

A rule is a function decorated with `@fac.rule`. Its parameters say which files it reads and writes: the annotation `fac.Input` marks a file it reads, `fac.Output` a file it writes, and each default is the path. Paths are exact and relative to the root, so `"about.txt"` would name a file beside `fac.py`, and Facere would fail rather than search the tree for one. `fac.out("about.html")` puts the page in the output directory, `build/`, as `build/about.html`.

The function's body, the recipe, is ordinary Python. *(0.2)* `fac.read_text` and `fac.write_text` read and replace a text file, with the same bytes on every OS.

Run `fac` in the directory holding `fac.py`:

```
$ fac
Finished in 18ms. Executed 1 rule.
$ fac
Finished in 14ms. No work to do. 1 output up to date.
```

Facere compares content, never timestamps, so a touched file is unchanged, while any edit to it is a change:

```
$ touch pages/about.txt
$ fac
Finished in 14ms. No work to do. 1 output up to date.
$ echo 'This site is built with Facere.' >> pages/about.txt
$ fac
Finished in 15ms. Executed 1 rule.
```

Facere compares the recipe's code too. Changing `<pre>` to `<div>` executes the rule again with no input changed, which `make` can't do. A comment in the recipe executes nothing, since Facere compares Python's syntax tree.

## Build every page: `*.txt` -> `*.html`

Replace `fac.py` with:

```python
import facere as fac

SOURCES = fac.sources("pages/*.txt")
PAGE_RULES = [{"source": source, "html": fac.out(source, ".html")} for source in SOURCES]


@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output):
    fac.write_text(html, f"<pre>{fac.read_text(source)}</pre>\n")
```

*(0.2)* `fac.sources` lists the files a glob matches, so a new page joins the build by existing. `each=` *(0.2)* takes a list of dicts and defines one rule for each, every key filling the parameter it names, so `PAGE_RULES` gives one rule per page. `fac.out("pages/about.txt", ".html")` swaps the suffix, giving `build/pages/about.html`.

Adding a page executes one rule:

```
$ fac
Finished in 16ms. Executed 1 rule.
$ printf 'Projects\n\nA birdhouse.\n' > pages/projects.txt
$ fac
Finished in 16ms. Executed 1 rule. 1 output up to date.
```

## Share a template and a value

Put the parts every page shares in `template.html`:

```
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{title} - {site}</title></head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>
```

Replace `fac.py` with:

```python
import facere as fac

SITE_NAME = "My site"
TEMPLATE = "template.html"
SOURCES = fac.sources("pages/*.txt")
PAGE_RULES = [{"source": source, "html": fac.out(source, ".html")} for source in SOURCES]


def fill(template, title, body):
    text = template.replace("{site}", SITE_NAME)
    return text.replace("{title}", title).replace("{body}", body)


@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output, template: fac.Input = TEMPLATE):
    paragraphs = fac.read_text(source).strip().split("\n\n")
    body = ""
    for paragraph in paragraphs[1:]:
        body += f"<p>{paragraph}</p>\n"
    fac.write_text(html, fill(fac.read_text(template), paragraphs[0], body))
```

Every page inputs the template, so editing it executes them all. Facere compares more than input files: a constant a recipe reads joins the rule's fingerprint, the hash that decides whether it is stale, meaning it must execute again, even when the recipe reaches it through a function such as `fill`. So a new `SITE_NAME` executes every page with no file changed:

```
$ fac
Finished in 18ms. Executed 2 rules.
$ sed -i 's/My site/Bonjour/' fac.py
$ fac
Finished in 19ms. Executed 2 rules.
```

Facere compares a value only if `fac.py` reads it as it loads. [Hidden inputs](./7-best-practices.md#hidden-inputs) lists what Facere cannot see.

## Add a home page: stop where nothing changed

Have each page also write its title to a file of its own, and build the home page from those:

```python
from pathlib import PurePosixPath

import facere as fac

SITE_NAME = "My site"
TEMPLATE = "template.html"
SOURCES = fac.sources("pages/*.txt")
PAGE_RULES = [
    {"source": source, "html": fac.out(source, ".html"), "title": fac.out(f"titles/{source}")}
    for source in SOURCES
]
TITLES = [rule["title"] for rule in PAGE_RULES]
INDEX = fac.out("pages/index.html")


def fill(template, title, body):
    text = template.replace("{site}", SITE_NAME)
    return text.replace("{title}", title).replace("{body}", body)


@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output, title: fac.Output, template: fac.Input = TEMPLATE):
    paragraphs = fac.read_text(source).strip().split("\n\n")
    body = ""
    for paragraph in paragraphs[1:]:
        body += f"<p>{paragraph}</p>\n"
    fac.write_text(title, paragraphs[0])
    fac.write_text(html, fill(fac.read_text(template), paragraphs[0], body))


@fac.rule
def index(
    titles: list[fac.Input] = TITLES, template: fac.Input = TEMPLATE, html: fac.Output = INDEX
):
    body = ""
    for title in titles:
        link = PurePosixPath(title).stem + ".html"
        body += f'<p><a href="{link}">{fac.read_text(title)}</a></p>\n'
    fac.write_text(html, fill(fac.read_text(template), "Home", body))
```

A rule may output several files, and `list[fac.Input]` marks a list of files read. `index` reads the files `page` writes, so Facere executes `page` first, whatever order the functions are in.

An edit now stops as soon as an output comes out the same. A new paragraph leaves the title unchanged, so the page executes and the home page does not. A new title reaches both:

```
$ fac
Finished in 21ms. Executed 3 rules.
$ printf '\nAnother paragraph.\n' >> pages/about.txt
$ fac
Finished in 20ms. Executed 1 rule. 3 outputs up to date.
$ sed -i '1s/About me/About/' pages/about.txt
$ fac
Finished in 21ms. Executed 2 rules. 2 outputs up to date.
```

A target is a name or output path given on the command line. With no target, `fac` builds every rule and executes no task, unless you mark what it builds with `default=True`, as in `@fac.rule(default=True)`. Two targets build less:

- `fac page` builds every page, by the rule's name
- `fac build/pages/about.html` builds one, by the path it outputs, relative to the root. A target holding a path separator is always a path

## Run a program: a sitemap

A recipe can run any program, such as a compiler, a formatter, or your own script. Put this script in `tools/sitemap.py`:

```python
"""Print the URL of each page: sitemap.py BASE_URL PAGE..."""

import sys

base_url = sys.argv[1]
for page in sys.argv[2:]:
    print(base_url + page)
```

Add these lines to `fac.py`, with `import sys`:

```python
BASE_URL = "https://example.com/"
SITEMAP_TOOL = "tools/sitemap.py"
PAGE_NAMES = [PurePosixPath(source).stem + ".html" for source in SOURCES]
SITEMAP = fac.out("pages/sitemap.txt")


@fac.rule
def sitemap(
    page_names: list[str] = PAGE_NAMES, tool: fac.Input = SITEMAP_TOOL, output: fac.Output = SITEMAP
):
    fac.run(sys.executable, tool, BASE_URL, "index.html", page_names, stdout=output)
```

`fac.run` runs one command, taking the program and each argument separately. A list, such as `page_names`, gives each of its strings as one argument, and `stdout=` names the file that receives the command's output. `sys.executable` is the Python running Facere, so the script runs the same on every OS. Facere runs commands without a shell, so `fac.run("python tools/sitemap.py")` looks for a program of that name, and fails. Separate arguments also need no quoting, so a path holding a space stays one argument on every OS.

Facere can't see inside a program, so declare what it reads. The script is an input, so editing it executes this rule alone. `list[str]` marks values that may look like paths but are never read as files, so editing a page leaves the sitemap up to date, while adding one changes the list and executes it. [Building a C program](./9-building-c.md) applies all this to a compiler.

## Preview and clean

Copy [`tools/live_server.py`](https://github.com/toasterparty/facere/tree/main/doc/examples/my-site/tools/live_server.py), a small server of the project's own, and add these lines to `fac.py`, with `import os` and `import shutil`:

```python
SERVER_TOOL = "tools/live_server.py"
SITE = [rule["html"] for rule in PAGE_RULES] + [INDEX, SITEMAP]


@fac.task
def serve(args: fac.Args, files: list[fac.Input] = SITE, tool: fac.Input = SERVER_TOOL):
    fac.run(sys.executable, tool, fac.out("pages"), args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
```

A task is a function decorated with `@fac.task` that executes whenever you ask. It reads files as a rule does but writes none that Facere tracks, and its commands print live. `fac serve` inputs every file of the site, so it builds whatever is stale, then serves the site at `http://localhost:8000` until you stop it. Leave it running, edit a page, and run `fac` in a second terminal: the open tab updates itself, since the server reloads a page when `build/pages` changes. *(planned)* `fac --watch serve` will rebuild on each save, with no second terminal. `fac clean` deletes the output directory, with Facere's state, its record of past builds, inside it. `fac.out()` *(0.2)* is that directory.

Targets build in the order given, so `fac clean serve` rebuilds from nothing, then serves. *(0.2)* Whatever follows `--` goes to a task's `fac.Args` parameter, so `fac serve -- 8080` picks another port.

Delete a page and its old HTML stays in `build/pages`, still served, until `fac clean`, since [Facere leaves orphaned outputs to you](./7-best-practices.md#orphaned-outputs).

## Run `fac` differently

| Flag | Effect |
| --- | --- |
| `-C path/to/project` | Run as if started in that directory, from anywhere |
| `--out build-debug` | Keep outputs and state in that directory instead of `build/`, leaving `build/` alone |
| `-q` | Hide the output of every successful command |
| `-v` *(0.2)* | Print each command, as one string, before it runs |

`-v` shows what `fac.run` made of its arguments. The pages and the home page run no command, since their recipes are plain Python:

```
$ fac clean
Finished in 19ms. Executed 1 task.
$ fac -v
/usr/bin/python3 tools/sitemap.py https://example.com/ index.html about.html projects.html
Finished in 40ms. Executed 4 rules.
```

`fac --help` documents every flag, target, and exit status.

## The finished `fac.py`

[`doc/examples/my-site/`](https://github.com/toasterparty/facere/tree/main/doc/examples/my-site) holds this project, whose comments recap what each edit executes:

```python
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
```

[<- Facere](./README.md) | [Writing a `fac.py` ->](./2-fac-py.md)
