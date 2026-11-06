# Parameterization

Build the same thing several ways by giving recipes different data. Every way below of supplying data to a rule joins its fingerprint, so a changed value executes just the rules that read it.

## Values

A parameter that is not an input or output holds a value, and so does a module constant a recipe reads:

```python
VERSION = "1.4.0"


@fac.rule
def version_header(path: fac.Output = fac.out("version.h")):
    fac.write_text(path, f'#define VERSION "{VERSION}"\n')
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

A configuration compiles the same sources with other flags, into a directory of its own. Plain `for` loops build the rows:

```python
ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CONFIGS = {"debug": ["-O0", "-g"], "release": ["-O2", "-g0"]}
SOURCES = fac.sources("src/*.c")

OBJECT_FILE_RULES = []
APP_RULES = []
for config in CONFIGS:
    objects = []
    for source in SOURCES:
        obj = fac.out(f"{config}/{source}", ".o")
        OBJECT_FILE_RULES.append({"source": source, "obj": obj, "cflags": CONFIGS[config]})
        objects.append(obj)
    APP_RULES.append({"objects": objects, "program": fac.out(f"{config}/app")})


@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, cflags):
    fac.run(CC, cflags, "-c", source, "-o", obj)


@fac.rule(each=APP_RULES)
def app(objects: list[fac.Input], program: fac.Output):
    fac.run(CC, objects, "-o", program)
```

`fac build/release/app` builds one configuration, and `fac app` builds both. Changing `-O2` executes only the release compiles. The [`c-configurations`](https://github.com/toasterparty/facere/tree/main/doc/examples/c-configurations) example runs this.

*(planned)* `with fac.scope("release"):` gives a configuration a name of its own, as in `fac server.release` or `fac '*.release'`.

`--out` instead keeps the same rules and values apart in another directory, as for a CI job.

## Per-machine values

Module-level code runs on every invocation, so a value it computes joins the fingerprint of each rule that reads it. `TOOLCHAIN = os.environ.get("TOOLCHAIN", "gcc")` executes what reads it whenever the variable changes, and a shared module *(0.2)* kept out of version control does the same for settings that differ per machine.

## Task arguments

*(0.2)* A task's parameter annotated `fac.Args` holds what follows `--` on the command line, a tuple of strings:

```python
@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)
```

`fac flash monitor -- /dev/ttyUSB0` passes the argument to both tasks.

Rules take no command-line arguments, since the record of a rule's last execution could not tell which ones it used.

[<- Writing a `fac.py`](./2-fac-py.md) | [Multiple `fac.py` files ->](./4-multiple-fac-py.md)
