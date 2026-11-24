import threading
from typing import assert_type

import facere as fac

_CALLS_LOCK = threading.Lock()


def version(tool):
    """Sign `tool` by the text of its .version file, noting each call in calls.txt, safely from several threads at once."""
    # Facere calls a signature on a worker thread, never the one that watches for signals.
    assert threading.current_thread() is not threading.main_thread()
    with _CALLS_LOCK, open("calls.txt", "a", encoding="utf-8") as calls:
        calls.write(f"{tool}\n")
    return fac.read_text(f"{tool}.version")


CC = fac.Virtual("cc", fingerprint=version)
LD = fac.Virtual("ld", fingerprint=version)
COMPILES = [{"unit": unit, "output": fac.out(f"{unit}.o")} for unit in ("a", "b", "c")]


@fac.rule(each=COMPILES, default=True)
def compile_(unit, output: fac.Output, compiler: fac.Input[fac.Virtual] = CC):
    # ty checks this, so a change to how fac.Input types a virtual source fails `fac test`.
    assert_type(compiler, fac.Virtual)
    fac.write_text(output, f"{unit} by {compiler.key}")


@fac.rule(default=True)
def link(linker: fac.Input[fac.Virtual] = LD, output: fac.Output = fac.out("app")):
    fac.write_text(output, f"linked by {linker.key}")


@fac.rule
def readme(output: fac.Output = fac.out("readme.txt")):
    fac.write_text(output, "local")


@fac.rule
def misread(compiler: fac.Input[fac.Virtual] = CC, output: fac.Output = fac.out("misread.txt")):
    fac.write_text(output, fac.read(compiler))
