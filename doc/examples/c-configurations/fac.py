"""One C program built two ways, each configuration compiling every source with flags of its own."""

import os
import shutil
import sys

import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
WARNINGS = ["-Wall", "-Wextra"]
CONFIGS = {
    "debug": ["-O0", "-g", '-DBUILD_NAME="debug"'],
    "release": ["-O2", "-s", '-DBUILD_NAME="release"'],
}
SOURCES = fac.sources("src/*.c")
HEADERS = fac.sources("src/*.h")
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


@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, cflags, headers: list[fac.Input] = HEADERS):
    fac.run(CC, WARNINGS, cflags, "-c", source, "-o", obj)


@fac.rule(each=APP_RULES, default=True)
def app(objects: list[fac.Input], program: fac.Output):
    fac.run(CC, objects, "-o", program)


@fac.task
def run_debug(args: fac.Args, program: fac.Input = DEBUG_PROGRAM):
    fac.run(program, args)


@fac.task
def run_release(args: fac.Args, program: fac.Input = RELEASE_PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
