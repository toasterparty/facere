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
