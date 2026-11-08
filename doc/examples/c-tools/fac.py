"""One C program with the tools a mature project runs around its build: a formatter, a static analyzer, a size summary, disassembly, valgrind, a version bump, and flashing."""

import os
import re
import shutil
import sys

import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CFLAGS = ["-O1", "-g", "-Wall", "-I.", "-DENABLE_HTTPS=1"]
SOURCES = fac.sources("src/*.c")
FORMATTED = fac.sources("src/*.c", "src/*.h")
VERSION_HEADER = "src/version.h"
VERSION_PARTS = ["major", "minor", "patch"]
FLASH_TOOL = "tools/flash.py"
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""
PROGRAM = fac.out(f"app{EXE_SUFFIX}")
BOARD = fac.out(f"board{EXE_SUFFIX}")
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


@fac.rule(each=OBJECT_FILE_RULES, cflags=CFLAGS)
def object_file(source: fac.Input, obj: fac.Output, cflags):
    fac.run(CC, cflags, "-MD", "-MF", f"{obj}.d", "-c", source, "-o", obj)
    fac.add_inputs(fac.c.makefile_deps(f"{obj}.d"))


@fac.rule(default=True)
def app(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(CC, objects, "-o", program)


@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)


@fac.task
def format_(files: list[fac.Input] = FORMATTED):
    fac.run("clang-format", "-i", files)


@fac.task
def check(sources: list[fac.Input] = SOURCES):
    fac.run("clang-check", sources, "--", "-I.", "-DENABLE_HTTPS=1")


@fac.task
def size(program: fac.Input = PROGRAM):
    fac.run("size", program)


@fac.task
def disassemble(args: fac.Args = ("main",), program: fac.Input = PROGRAM):
    """Print the functions named after --, by default main."""
    for symbol in args:
        fac.run("objdump", "--disassemble=" + symbol, program)


@fac.task
def valgrind(program: fac.Input = PROGRAM):
    fac.run("valgrind", "--error-exitcode=1", "--quiet", program)


@fac.task
def bump(args: fac.Args, header: fac.Input = VERSION_HEADER):
    """Raise the major, minor, or patch version named after --, zeroing the parts after it."""
    assert len(args) == 1 and args[0] in VERSION_PARTS, f"pick one of {VERSION_PARTS}"
    part = VERSION_PARTS.index(args[0])
    text = fac.read_text(header)
    version = re.findall(r"\d+\.\d+\.\d+", text)[0]
    numbers = [int(number) for number in version.split(".")]
    raised = numbers[:part] + [numbers[part] + 1] + [0] * (2 - part)
    fac.write_text(header, text.replace(version, ".".join(str(number) for number in raised)))


@fac.task
def flash(args: fac.Args, program: fac.Input = PROGRAM, tool: fac.Input = FLASH_TOOL):
    """Write the program to the port named after -- by -p or --port, by default the board file."""
    fac.run(sys.executable, tool, program, "--port", BOARD, args)


@fac.task
def monitor():
    """Run what the last flash wrote to the board file."""
    fac.run(BOARD)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
