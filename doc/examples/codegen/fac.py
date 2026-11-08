"""A C program whose message structs come from a Python generator and whose keyword lookup comes from gperf."""

import os
import shutil
import sys

from tools import messages

import facere as fac

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
CFLAGS = ["-O2", "-Wall", "-I.", "-I" + fac.out("gen")]
SPECS = fac.sources("messages/*.toml")
KEYWORD_TABLE = "src/keywords.gperf"
KEYWORDS = fac.out("gen/keywords.c")
PROGRAM = fac.out("server.exe" if sys.platform == "win32" else "server")
MESSAGE_RULES = [
    {"spec": spec, "header": fac.out(f"gen/{spec}", ".h"), "source": fac.out(f"gen/{spec}", ".c")}
    for spec in SPECS
]
HEADERS = [rule["header"] for rule in MESSAGE_RULES]
SOURCES = fac.sources("src/**/*.c") + [rule["source"] for rule in MESSAGE_RULES] + [KEYWORDS]
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


@fac.rule(each=MESSAGE_RULES)
def message(spec: fac.Input, header: fac.Output, source: fac.Output):
    messages.generate(spec, header, source)


@fac.rule
def keywords(table: fac.Input = KEYWORD_TABLE, source: fac.Output = KEYWORDS):
    fac.run("gperf", "--language=ANSI-C", f"--output-file={source}", table)


@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, headers: list[fac.OrderOnly] = HEADERS):
    fac.run(CC, CFLAGS, "-MD", "-MF", f"{obj}.d", "-c", source, "-o", obj)
    fac.add_inputs(fac.c.makefile_deps(f"{obj}.d"))


@fac.rule(default=True)
def server(objects: list[fac.Input] = OBJECTS, program: fac.Output = PROGRAM):
    fac.run(CC, objects, "-o", program)


@fac.task
def run(args: fac.Args, program: fac.Input = PROGRAM):
    fac.run(program, args)


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
