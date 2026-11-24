"""A C program whose message structs come from a Python generator and whose keyword lookup comes from gperf. Compiling needs `uv`, whose `uvx` runs the compiler, and `keywords` needs `gperf`."""

import os
import shutil
import sys

import facere as fac

# A plain module that knows nothing of Facere.
from tools import messages

ZIG_VERSION = "0.16.0"
CC = ["uvx", "--from", f"ziglang=={ZIG_VERSION}", "python-zig", "cc"]
# A path glued to -I escapes the check that fails a command given an undeclared path. That costs
# nothing here, since the generated headers are already inputs.
CFLAGS = ["-O2", "-Wall", "-I.", "-I" + fac.out("gen")]
# A new spec executes its `message`, the compile of its source, and the link.
SPECS = fac.sources("messages/*.toml")
GENERATOR = "tools/messages.py"
KEYWORD_TABLE = "src/keywords.gperf"
KEYWORDS = fac.out("gen/keywords.c")
PROGRAM = fac.out("server.exe" if sys.platform == "win32" else "server")
# Naming each file while fac.py loads makes it a declared output that compiles on its own. A generator
# choosing its own names, as protoc does, would output a directory, and one rule would compile it all.
MESSAGE_RULES = [
    {"spec": spec, "header": fac.out(f"gen/{spec}", ".h"), "source": fac.out(f"gen/{spec}", ".c")}
    for spec in SPECS
]
HEADERS = [rule["header"] for rule in MESSAGE_RULES]
# Generated sources land in build/gen/, which the glob never reaches, and their objects stay beside
# them, since fac.out keeps a path already in the output directory.
SOURCES = fac.sources("src/**/*.c") + [rule["source"] for rule in MESSAGE_RULES] + [KEYWORDS]
OBJECT_FILE_RULES = [{"source": source, "obj": fac.out(source, ".o")} for source in SOURCES]
OBJECTS = [rule["obj"] for rule in OBJECT_FILE_RULES]


# A fingerprint holds the recipe's own code, not the generator's it calls, so the generator is an
# input: any edit to it executes every `message`, and only a changed generated text goes further.
# Called as a function, the generator needs no command-line entry.
@fac.rule(each=MESSAGE_RULES)
def message(
    spec: fac.Input, header: fac.Output, source: fac.Output, generator: fac.Input = GENERATOR
):
    messages.generate(spec, header, source)


# A missing gperf fails only when this rule must execute, with fac.run naming the program.
@fac.rule
def keywords(table: fac.Input = KEYWORD_TABLE, source: fac.Output = KEYWORDS):
    fac.run("gperf", "--language=ANSI-C", f"--output-file={source}", table)


# A depfile is a Makefile fragment: the object, a colon, then each file the compile read. A space
# in a path is written `\ `, and a trailing `\` continues a line.
def parse_depfile(path):
    text = fac.read_text(path).replace("\\\n", " ").replace("\\ ", "\0")
    files = text.partition(": ")[2].split()
    return [file.replace("\0", " ") for file in files]


# Order-only headers are built before any compile, and make it stale only once its depfile lists them.
# Drop `headers` and the compile fails, naming the rule that outputs the header it read, since nothing
# orders it after the generator. The price is that the first run waits for every header.
# The list joins each compile's fingerprint, so a new header executes every compile, though only
# those that come to include it can produce different bytes.
# A new file named as a header a compile read, such as a login.h at the root, might shadow it.
# Facere compares names alone, so each such compile executes.
@fac.rule(each=OBJECT_FILE_RULES)
def object_file(source: fac.Input, obj: fac.Output, headers: list[fac.OrderOnly] = HEADERS):
    fac.run(CC, CFLAGS, "-MD", "-MF", f"{obj}.d", "-c", source, "-o", obj)
    fac.add_inputs(parse_depfile(f"{obj}.d"))


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
