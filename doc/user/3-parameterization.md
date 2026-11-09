# Parameterization

Build the same thing several ways by giving recipes different data. Every way below of supplying data to a rule joins its fingerprint, so a changed value executes just the rules that read it.

## Values

A parameter that is not an input or output holds a value, and so does a module constant a recipe reads:

```python
VERSION = "1.4.0"


@fac.rule
def version_file(path: fac.Output = fac.out("version.txt")):
    fac.write_text(path, f"{VERSION}\n")
```

A keyword argument to the decorator fills the parameter it names, and the decorators return the function unchanged, so one function can define rules one after another:

```python
@fac.rule(path=fac.out("en.txt"), text="hello")
@fac.rule(path=fac.out("fr.txt"), text="bonjour")
def greeting(path: fac.Output, text: str):
    fac.write_text(path, text)
```

`fac greeting` builds both. Annotate a value `str` where it may look like a path, since an unannotated value naming a file under the root is an error.

## Rows

`each=` *(0.2)* defines one rule per dict in a list, each key filling the parameter it names:

```python
PAGE_RULES = [{"source": source, "html": fac.out(source, ".html")} for source in PAGES]


@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output):
    fac.write_text(html, render(fac.read_text(source)))
```

`fac page` builds them all, and the path of one's output builds that one. A failure names the one that failed, as `rule 'page' (build/about.html)`.

## Configurations

A configuration builds the same sources with other values, into a directory of its own. A plain `for` loop builds the list of dicts:

```python
CONFIGS = {"staging": "https://staging.example.com/", "production": "https://example.com/"}
SOURCES = fac.sources("pages/*.txt")

PAGE_RULES = []
for config in CONFIGS:
    for source in SOURCES:
        html = fac.out(f"{config}/{source}", ".html")
        PAGE_RULES.append({"source": source, "html": html, "base_url": CONFIGS[config]})


@fac.rule(each=PAGE_RULES)
def page(source: fac.Input, html: fac.Output, base_url):
    fac.write_text(html, fac.read_text(source).replace("{url}", base_url))
```

`fac build/production/pages/about.html` builds one page of one configuration, and `fac page` builds every page of both. Changing the production URL executes only the production pages. [Building a C program](./9-building-c.md#debug-and-release) applies this to debug and release.

*(planned)* `with fac.scope("release"):` gives a configuration a name of its own, as in `fac server.release` or `fac '*.release'`.

`--out` instead keeps the same rules and values apart in another directory, as for a CI job.

## Per-machine values

Module-level code runs on every invocation, so a value it computes joins the fingerprint of each rule that reads it. `TOOLCHAIN = os.environ.get("TOOLCHAIN", "gcc")` executes what reads it whenever the variable changes, and a shared module *(0.2)* kept out of version control does the same for settings that differ per machine.

## Task arguments

*(0.2)* A task's parameter annotated `fac.Args` holds what follows `--` on the command line, a tuple of strings:

```python
@fac.task
def serve(args: fac.Args, files: list[fac.Input] = SITE):
    fac.run(sys.executable, "-m", "http.server", args, "--directory", fac.out("pages"))
```

Each task in one invocation gets the same arguments.

Rules take no command-line arguments, since the record of a rule's last execution could not tell which ones it used.

[<- Writing a `fac.py`](./2-fac-py.md) | [Multiple `fac.py` files ->](./4-multiple-fac-py.md)
