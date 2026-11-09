"""One C program built two ways, each configuration compiling every source with flags of its own. It needs `uv`, whose `uvx` runs the compiler."""

import os
import shutil
import sys

import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
WARNINGS = ["-Wall", "-Wextra"]
# Change release's BUILD_NAME and release's compiles and link execute, while debug's stay up to date.
CONFIGS = {
    "debug": ["-O0", "-g", '-DBUILD_NAME="debug"'],
    "release": ["-O2", "-s", '-DBUILD_NAME="release"'],
}
SOURCES = fac.sources("src/*.c")
PROGRAM_NAME = "app.exe" if sys.platform == "win32" else "app"

OBJECT_FILE_RULES = []
APP_RULES = []
for config in CONFIGS:
    objects = []
    for source in SOURCES:
        obj = fac.out(f"{config}/{source}", ".o")
        OBJECT_FILE_RULES.append({"source": source, "obj": obj, "cflags": CONFIGS[config]})
        objects.append(obj)
    APP_RULES.append({"objects": objects, "program": fac.out(f"{config}/{PROGRAM_NAME}")})

DEBUG_PROGRAM = fac.out(f"debug/{PROGRAM_NAME}")
RELEASE_PROGRAM = fac.out(f"release/{PROGRAM_NAME}")


# Editing a header executes the compiles whose depfiles list it, in each configuration.
@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, cflags):
    fac.run(CC, WARNINGS, cflags, "-MD", "-MF", f"{obj}.d", "-c", source, "-o", obj)
    fac.add_inputs(fac.c.makefile_deps(f"{obj}.d"))


# `fac build/release/app` names one program by its path, and builds only what it needs.
@fac.rule(each=APP_RULES, default=True)
def app(objects: list[fac.Input], program: fac.Output):
    fac.run(CC, objects, "-o", program)


@fac.task
def run_debug(args: fac.Args, program: fac.Input = DEBUG_PROGRAM):
    fac.run(program, args)


# `fac run_release -- a b` builds the release if stale, then runs it with what follows `--`.
@fac.task
def run_release(args: fac.Args, program: fac.Input = RELEASE_PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
