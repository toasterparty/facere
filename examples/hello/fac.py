"""Build hello world with zig's C compiler, which the ziglang package on PyPI ships for Linux, macOS, and Windows."""

import sys

import facere as fac

ZIG_CC = ["uvx", "--from", "ziglang==0.16.0", "python-zig", "cc"]
CFLAGS = ["-O2", "-Wall", "-Wextra"]
SOURCES = ["hello.c"]
OBJECTS = [fac.out(source, ".o") for source in SOURCES]
PROGRAM = fac.out("hello.exe" if sys.platform == "win32" else "hello")


@fac.rule(each=zip(SOURCES, OBJECTS))
def object_file(source: fac.Input, obj: fac.Output):
    fac.run(ZIG_CC, CFLAGS, "-c", source, "-o", obj)


@fac.rule(default=True)
def hello(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(ZIG_CC, CFLAGS, objects, "-o", program)


@fac.task
def run(program: fac.Input = PROGRAM):
    fac.run(program)
