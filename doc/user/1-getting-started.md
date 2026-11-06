# Getting started

Install Facere on Python 3.11 or newer with `uv tool install facere` or `pipx install facere`, which install it in an environment of its own and put the `fac` command on your `PATH`. Check that it runs:

```
$ fac --version
0.2.0
```

A project's rules live in a file named `fac.py` in its top directory, the root. The steps below grow one `fac.py` that builds a C program.

## Compile `main.c` -> `app`

Put a C program in `src/main.c`, and this in `fac.py`, beside `src/`:

```python
import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]


@fac.rule
def app(source: fac.Input = "src/main.c", program: fac.Output = fac.out("app")):
    fac.run(CC, "-O2", source, "-o", program)
```

A rule is a function decorated with `@fac.rule`. Its parameters say which files it reads and writes: the annotation `fac.Input` marks a file it reads, `fac.Output` a file it writes, and each default is the path. Paths are exact and relative to the root, so `"main.c"` would name a file beside `fac.py`, and Facere would fail rather than search the tree for one. `fac.out("app")` puts the program in the output directory, `build/`, as `build/app`.

The function's body, the recipe, runs one command through `fac.run`, which takes the program and each argument separately. A list, such as `CC`, gives each of its strings as one argument. `CC` runs the C compiler in the `ziglang` package through `uvx`, which comes with uv, so you need no compiler installed. The first run downloads about 90 MiB. To use a compiler you already have, write `CC = ["cc"]`. Facere runs commands without a shell, so `fac.run("cc -O2 src/main.c")` looks for a program named `cc -O2 src/main.c`, and fails. Separate arguments also need no quoting, so a path holding a space stays one argument on every OS.

Run `fac` in the directory holding `fac.py`:

```
$ fac
Finished in 335ms. Executed 1 rule.
$ fac
Finished in 17ms. No work to do. 1 output up to date.
```

Facere compares content, never timestamps, so a touched file is unchanged, while any edit to it is a change:

```
$ touch src/main.c
$ fac
Finished in 17ms. No work to do. 1 output up to date.
$ echo '// comment' >> src/main.c
$ fac
Finished in 111ms. Executed 1 rule.
```

Facere does not read C, so it cannot tell that the new bytes are only a comment. Changing `"-O2"` also executes the rule again, since the recipe's code is part of what Facere compares. A comment in the recipe does not, since Facere compares Python's syntax tree.

## Compile `main.c` -> `main.o` -> `app`

```python
import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CFLAGS = ["-O2", "-s", "-Wall"]
SOURCE = "src/main.c"
OBJECT = fac.out("src/main.o")
PROGRAM = fac.out("app")


@fac.rule
def object_file(source: fac.Input = SOURCE, obj: fac.Output = OBJECT):
    fac.run(CC, CFLAGS, "-c", source, "-o", obj)


@fac.rule(default=True)
def app(obj: fac.Input = OBJECT, program: fac.Output = PROGRAM):
    fac.run(CC, obj, "-o", program)
```

`app` reads the file `object_file` writes, so Facere executes `object_file` first, whatever order the functions are in.

An edit now stops as soon as an output comes out the same. A comment leaves the object's bytes unchanged, so the compile executes and the link does not. `-s` keeps that true by stripping debug info, in which zig records where it compiled:

```
$ echo '// comment' >> src/main.c
$ fac
Finished in 102ms. Executed 1 rule. 1 output up to date.
```

`default=True` makes `app` what a bare `fac` builds, so `fac` and `fac app` build the same thing. A `fac.py` may mark several rules and tasks `default=True`, and `fac` builds them all. With no default, as in the last step, `fac` builds every rule and executes no task.

A target is a name or output path given on the command line. Two build only `main.o`, and neither links the program:

- `fac object_file`, by the rule's name
- `fac build/src/main.o`, by the path it outputs, relative to the root. A target holding a path separator is always a path

## Compile `*.c` -> `*.o` -> `app`

Move part of the program into `src/greeting.c` and `src/greeting.h`, and list the files instead of naming each one:

```python
import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CFLAGS = ["-O2", "-s", "-Wall"]
SOURCES = fac.sources("src/*.c")
HEADERS = fac.sources("src/*.h")
PROGRAM = fac.out("app")
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, headers: list[fac.Input] = HEADERS):
    fac.run(CC, CFLAGS, "-c", source, "-o", obj)


@fac.rule(default=True)
def app(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(CC, objects, "-o", program)
```

*(0.2)* `fac.sources` lists the files a glob matches, so a new `.c` file joins the build by existing. `each=` *(0.2)* takes a list of dicts and defines one rule for each, every key filling the parameter it names, so `OBJECT_FILE_RULES` gives one compile per source. `fac.out("src/main.c", ".o")` swaps the suffix, giving `build/src/main.o`. The rows are ordinary data, so `OBJECTS` reads the object paths back out of them for the link. `list[fac.Input]` marks a list of files read.

Each compile inputs every header, though its recipe never names `headers`: an input is what Facere watches, and Facere watches nothing undeclared. Editing a header therefore executes every compile, until *(planned)* a recipe can report just the headers its compiler read. Editing one source executes one compile, then the link if its object changed:

```
$ echo '// comment' >> src/greeting.c
$ fac
Finished in 96ms. Executed 1 rule. 2 outputs up to date.
```

`fac object_file` now builds every object, while `fac build/src/main.o` still builds one.

## Run and clean `app`

```python
@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
```

A task is a function decorated with `@fac.task` that executes whenever you ask. It reads files as a rule does but writes none that Facere tracks, and its commands print live. `fac run` links the program if `app` is stale, then runs it, every time, and `fac clean` deletes the output directory, with Facere's state, its record of past builds, inside it. `fac.out()` *(0.2)* is that directory, and `clean` needs `import os` and `import shutil`.

Targets build in the order given, so `fac clean run` rebuilds from nothing, then runs. *(0.2)* Whatever follows `--` goes to a task's `fac.Args` parameter, so `fac run -- --verbose input.txt` gives the program those two arguments.

On Windows the program needs an `.exe` suffix. Add `import sys` and pick the name by platform:

```python
PROGRAM = fac.out("app.exe" if sys.platform == "win32" else "app")
```

## Rebuild when a setting changes

Facere compares more than input files. Make the greeting a setting of the build: have `src/greeting.c` print a macro, with `puts(GREETING);`, and take its value from the environment:

```python
GREETING = os.environ.get("GREETING", "hello, world")
CFLAGS = ["-O2", "-s", "-Wall", f'-DGREETING="{GREETING}"']
```

No file changes when `GREETING` does, yet a constant a recipe reads joins the rule's fingerprint, the hash that decides whether it is stale. The compiles therefore execute with each new value, and the link follows since `greeting.o` came out different:

```
$ fac
Finished in 20ms. No work to do. 3 outputs up to date.
$ GREETING=bonjour fac run
bonjour
Finished in 251ms. Executed 1 task and 3 rules.
```

`ZIG_VERSION` works the same way, so changing it executes every rule that reads `CC`, with the new compiler.

Only what `fac.py` reads as it loads gets compared. Called inside the recipe, `os.environ.get` would run only when the rule already executes, so a new value would change nothing. [Hidden inputs](./7-best-practices.md#hidden-inputs) lists everything else Facere cannot see.

## Run `fac` differently

| Flag | Effect |
| --- | --- |
| `-C path/to/project` | Run as if started in that directory, from anywhere |
| `--out build-debug` | Keep outputs and state in that directory instead of `build/`, leaving `build/` alone |
| `-q` | Hide the output of every successful command |
| `-v` *(0.2)* | Print each command, as one string, before it runs |

`-v` shows what `fac.run` made of its arguments:

```
$ fac clean
Finished in 19ms. Executed 1 task.
$ fac -v
uvx --from ziglang==0.16.0 python-zig cc -O2 -s -Wall '-DGREETING="hello, world"' -c src/greeting.c -o build/src/greeting.o
uvx --from ziglang==0.16.0 python-zig cc -O2 -s -Wall '-DGREETING="hello, world"' -c src/main.c -o build/src/main.o
uvx --from ziglang==0.16.0 python-zig cc build/src/greeting.o build/src/main.o -o build/app
Finished in 202ms. Executed 3 rules.
```

`fac --help` documents every flag, target, and exit status.

## The finished `fac.py`

[`doc/examples/hello-world/`](https://github.com/toasterparty/facere/tree/main/doc/examples/hello-world) holds this project:

```python
import os
import shutil
import sys

import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
GREETING = os.environ.get("GREETING", "hello, world")
CFLAGS = ["-O2", "-s", "-Wall", f'-DGREETING="{GREETING}"']
SOURCES = fac.sources("src/*.c")
HEADERS = fac.sources("src/*.h")
PROGRAM = fac.out("app.exe" if sys.platform == "win32" else "app")
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, headers: list[fac.Input] = HEADERS):
    fac.run(CC, CFLAGS, "-c", source, "-o", obj)


@fac.rule(default=True)
def app(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(CC, objects, "-o", program)


@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
```

[<- Facere](./README.md) | [Writing a `fac.py` ->](./2-fac-py.md)
