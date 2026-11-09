# Building a C program

This page assumes [getting started](./1-getting-started.md), and grows one `fac.py` that builds a C program.

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

`CC` runs the C compiler in the `ziglang` package through `uvx`, which comes with uv, so with uv installed you need no compiler. The first run downloads about 90 MiB. To use a compiler you already have, write `CC = ["cc"]`.

```
$ fac
Finished in 335ms. Executed 1 rule.
$ fac
Finished in 17ms. No work to do. 1 output up to date.
$ echo '// comment' >> src/main.c
$ fac
Finished in 111ms. Executed 1 rule.
```

Facere does not read C, so it cannot tell that the new bytes are only a comment. Changing `"-O2"` also executes the rule again, since the recipe's code is part of what Facere compares.

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

A comment now leaves the object's bytes unchanged, so the compile executes and the link does not. `-s` keeps that true by stripping debug info, in which zig records where it compiled:

```
$ fac
Finished in 180ms. Executed 2 rules.
$ echo '// comment' >> src/main.c
$ fac
Finished in 102ms. Executed 1 rule. 1 output up to date.
```

`default=True` makes `app` what a bare `fac` builds, so `fac` and `fac app` build the same thing. `fac object_file` or `fac build/src/main.o` builds the object without linking.

## Compile `*.c` -> `*.o` -> `app`

Move part of the program into `src/greeting.c` and `src/greeting.h`, and list the files instead of naming each one:

```python
import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CFLAGS = ["-O2", "-s", "-Wall"]
SOURCES = fac.sources("src/*.c")
PROGRAM = fac.out("app")
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output):
    fac.run(CC, CFLAGS, "-MD", "-MF", f"{obj}.d", "-c", source, "-o", obj)
    fac.add_inputs(fac.c.makefile_deps(f"{obj}.d"))


@fac.rule(default=True)
def app(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(CC, objects, "-o", program)
```

Only the compiler knows which headers a source includes, so each compile passes `-MD -MF` to have it write a depfile, a Makefile fragment listing the files it read. *(0.4)* `fac.c.makefile_deps` reads that list and `fac.add_inputs` reports it, so editing a header executes just the compiles that read it. Editing one source executes one compile, then the link if its object changed:

```
$ fac
Finished in 240ms. Executed 3 rules.
$ echo '// comment' >> src/greeting.c
$ fac
Finished in 96ms. Executed 1 rule. 2 outputs up to date.
```

Name each depfile after the rule's own output, since output paths are unique. Facere cannot see writes, so two compiles sharing one depfile name race under `-j` *(planned)*, and the invocation still passes:

```python
# Bad: every compile writes the same depfile
fac.run(CC, CFLAGS, "-MD", "-MF", fac.out("deps.d"), "-c", source, "-o", obj)
```

## Run and clean `app`

Add these lines to `fac.py`, with `import os` and `import shutil`:

```python
@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
```

`fac run` links the program if `app` is stale, then runs it, every time, so `fac clean run` rebuilds from nothing, then runs, and `fac run -- --verbose input.txt` gives the program those two arguments.

On Windows the program needs an `.exe` suffix. Add `import sys` and pick the name by platform:

```python
PROGRAM = fac.out("app.exe" if sys.platform == "win32" else "app")
```

## Rebuild when the environment changes

Have `src/greeting.c` print a macro, with `puts(GREETING);`, and take its value from the environment:

```python
GREETING = os.environ.get("GREETING", "hello, world")
CFLAGS = ["-O2", "-s", "-Wall", f'-DGREETING="{GREETING}"']
```

`fac.py` reads the variable as it loads, so the value joins the fingerprint of each rule reading `CFLAGS`. The compiles execute with each new value, and the link follows since `greeting.o` came out different. `ZIG_VERSION` works the same way, so changing it executes every rule that reads `CC`, with the new compiler.

```
$ fac
Finished in 240ms. Executed 3 rules.
$ GREETING=bonjour fac run
bonjour
Finished in 251ms. Executed 1 task and 3 rules.
```

Called inside the recipe, `os.environ.get` would run only when the rule already executes, so a new value would change nothing.

`-v` shows what `fac.run` made of its arguments:

```
$ fac clean
Finished in 19ms. Executed 1 task.
$ fac -v
uvx --from ziglang==0.16.0 python-zig cc -O2 -s -Wall '-DGREETING="hello, world"' -MD -MF build/src/greeting.o.d -c src/greeting.c -o build/src/greeting.o
uvx --from ziglang==0.16.0 python-zig cc -O2 -s -Wall '-DGREETING="hello, world"' -MD -MF build/src/main.o.d -c src/main.c -o build/src/main.o
uvx --from ziglang==0.16.0 python-zig cc build/src/greeting.o build/src/main.o -o build/app
Finished in 202ms. Executed 3 rules.
```

## Debug and release

A configuration compiles the same sources with other flags, into a directory of its own. Plain `for` loops build the list of dicts:

```python
ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CONFIGS = {"debug": ["-O0", "-g"], "release": ["-O2", "-s"]}
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

## The finished `fac.py`

[`doc/examples/c-hello/`](https://github.com/toasterparty/facere/tree/main/doc/examples/c-hello) holds this project, without the configurations. [`c-tools`](https://github.com/toasterparty/facere/tree/main/doc/examples/c-tools) adds the tools a mature project runs around its build, and [`codegen`](https://github.com/toasterparty/facere/tree/main/doc/examples/codegen) adds generated sources:

```python
"""A C program compiled one source at a time and linked. It needs `uv`, whose `uvx` runs the compiler."""

import os
import shutil
import sys

import facere as fac

# A new version executes every rule that reads CC, with the new compiler.
ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
# Read as fac.py loads, so a new value executes the compiles. Read in a recipe, it never would.
GREETING = os.environ.get("GREETING", "hello, world")
# -s strips the debug info where zig records where it compiled, so a comment added to a source
# leaves its object the same.
CFLAGS = ["-O2", "-s", "-Wall", f'-DGREETING="{GREETING}"']
# A new .c file joins the build by existing.
SOURCES = fac.sources("src/*.c")
PROGRAM = fac.out("app.exe" if sys.platform == "win32" else "app")
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


# Only the compiler knows which headers a source includes. Its depfile lists them, so editing a
# header executes just the compiles that read it.
@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output):
    fac.run(CC, CFLAGS, "-MD", "-MF", f"{obj}.d", "-c", source, "-o", obj)
    fac.add_inputs(fac.c.makefile_deps(f"{obj}.d"))


# An object that comes out the same leaves this up to date.
@fac.rule(default=True)
def app(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(CC, objects, "-o", program)


# Links the program if it is stale, then runs it with what follows `--`, as in `fac run -- a b`.
@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
```

[<- Terminology](./8-terminology.md)
