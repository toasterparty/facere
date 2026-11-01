# Getting started

Facere builds a project from rules written in plain Python, in a file named `fac.py` in the project's top directory, the root. Install it on Python 3.11 or newer with `uv tool install facere` or `pip install facere`, which puts the `fac` command on your `PATH`.

## A first build

This `fac.py` compiles two C sources and links them into a program:

```python
import sys

import facere as fac

CFLAGS = ["-O2", "-Wall"]
SOURCES = ["main.c", "util.c"]
OBJECTS = [fac.out(source, ".o") for source in SOURCES]
PROGRAM = fac.out("app.exe" if sys.platform == "win32" else "app")


@fac.rule(each=zip(SOURCES, OBJECTS))
def object_file(source: fac.Input, obj: fac.Output):
    fac.run("cc", CFLAGS, "-c", source, "-o", obj)


@fac.rule(default=True)
def app(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run("cc", objects, "-o", program)


@fac.task
def run(program: fac.Input = PROGRAM):
    fac.run(program)
```

Run `fac` in the directory holding `fac.py`. It compiles both sources, links `build/app`, and prints a one-line summary. Run it again and nothing executes, since nothing changed. Edit `util.c` and only its compile and the link execute.

## Rules

A rule is a function decorated with `@fac.rule`, and its signature declares what it reads and writes. Each parameter's annotation decides what it holds:

| Annotation | Holds |
| --- | --- |
| `fac.Input`, `list[fac.Input]` | Inputs, the files or directories the rule reads |
| `fac.Output`, `list[fac.Output]` | Outputs, the files or directories the rule writes. Every rule has at least one |
| Anything else, or none | A value: data the rule uses that is not a file, such as a flag or a version string |

The function's body is the rule's recipe. Facere executes it only when an output is needed and out of date, after creating each output's parent directory.

Each parameter is filled from one of:

- its default
- a keyword argument to `@fac.rule`, which fills the parameter it names
- `each=`, an iterable of tuples, which defines one rule per tuple and fills the leading parameters in order. `object_file` above defines two rules that share one name.

Write paths as strings relative to the directory holding `fac.py`, with `/` separators on every OS. A value that names a file under the root is an error, since Facere cannot tell whether the rule reads it: annotate the parameter `fac.Input`, or `str` if the string only happens to look like a path.

Rules connect through paths alone. `app` inputs the paths `object_file` outputs, so both compiles execute before the link, whatever order the rules are defined in. An input that no rule outputs is a source, and must exist.

## The output directory

`fac.out` places an output in the output directory, `build/` by default, at the same relative path as the file it comes from, with its suffix swapped when you pass one: `fac.out("src/main.c", ".o")` is `build/src/main.o`, and `fac.out("app")` is `build/app`. A rule may still output any path.

Facere keeps its state, its record of past builds, in the output directory too. Deleting the directory forgets everything, so the next build executes every rule.

## Commands

`fac.run` runs one command and returns its standard output as text. It runs without a shell, so pass the program and each argument separately: `fac.run("cc", "-c", source)`, never `fac.run("cc -c main.c")`. A list or tuple of strings passes each of its items as one argument, as `CFLAGS` and `objects` do above. A command that exits non-zero fails the recipe, and so does any exception the recipe raises, an `assert` included.

In a rule, a command reads an empty standard input and its output is printed once it finishes. Keyword arguments adjust that:

| Argument | Effect |
| --- | --- |
| `stdin=`, `stdout=`, `stderr=` | Name a file to read standard input from or write a stream to. A file both `stdout=` and `stderr=` name gets both streams. |
| `env=` | Set environment variables over the inherited ones. `None` unsets a variable. |
| `cwd=` | Run in another directory, relative to the root. |
| `quiet=True` | Hide the command's output when it succeeds. |
| `timeout=` | Kill the command after that many seconds, failing the recipe. |

## Tasks

A task is a function decorated with `@fac.task`, for work that must happen whenever you ask, such as running tests, a server, or a deploy. It takes inputs and values but no outputs, and executes every time `fac` is asked for it, after the rules that output its inputs. Its commands print live and read from the terminal. `fac run` above links the program if it is out of date, then runs it.

## Running fac

A target's name is its function's name, less one trailing underscore, so `def import_` is named `import`. Pass `name=` to `@fac.rule` or `@fac.task` to choose another.

| Command | Builds |
| --- | --- |
| `fac` | The defaults, every rule and task declared with `default=True` |
| `fac app run` | Each target, in the order given |
| `fac object_file` | Every rule a name covers, here both compiles |
| `fac build/main.o` | Only the rule that outputs that path, relative to the root |
| `fac -C DIR` | As if started in `DIR`, which holds the `fac.py` |
| `fac --out DIR` | With the output directory at `DIR`, relative to the root |
| `fac -q` | Hiding the output of every successful command |

Before executing any recipe, Facere loads `fac.py` and checks every rule, so a mistake such as two rules outputting one path, a missing source, or a dependency cycle fails at once, naming the `fac.py` lines involved.

## When a rule executes

Facere compares content, never timestamps. A rule executes when any of these changes:

- the content of an input
- the files in a directory input, when one appears or disappears
- its recipe's code
- a value or module constant the recipe reads
- a program its commands launch, as when a compiler is upgraded in place
- one of its outputs, deleted or edited by hand

Comments, docstrings, and reformatting change nothing. A rule downstream executes only if an output it inputs comes out different.

Facere cannot see what a recipe reads behind its back, such as an environment variable inherited from your shell or a file it never declared. [Best practices](./best-practices.md) covers those risks, and [Terminology](./terminology.md) defines each term these pages use.
