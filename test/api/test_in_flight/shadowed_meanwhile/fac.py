import os
import time

import facere as fac

GENERATED = fac.out("gen")


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


# Writes a header named as one `compile` reads, once `compile` is executing.
@fac.rule
def generate(folder: fac.Output = GENERATED):
    wait_for(fac.out("compile.started"))
    os.makedirs(folder, exist_ok=True)
    fac.write_text(f"{folder}/config.h", "generated")


# Starts once Facere has hashed the generated directory, and so found the new header in it.
@fac.rule
def after(folder: fac.Input = GENERATED, target: fac.Output = fac.out("after.txt")):
    fac.write_text(target, "done")


# Nothing orders it after `generate`, so it executes while the header appears.
@fac.rule
def compile(source: fac.Input = "main.c", target: fac.Output = fac.out("main.o")):
    open(fac.out("compile.started"), "w").close()
    wait_for(fac.out("after.txt"))
    fac.add_inputs(["include/config.h"])
    fac.write_text(target, fac.read_text(source))
