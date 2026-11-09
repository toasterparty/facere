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
