import os
import time

import facere as fac

TEXT = fac.out("x.txt")


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


@fac.rule
def write(target: fac.Output = TEXT):
    fac.write_text(target, "good")


# Still executing when `vandal` overwrites what it inputs.
@fac.rule
def reader(text: fac.Input = TEXT, target: fac.Output = fac.out("reader.txt")):
    open(fac.out("reader.started"), "w").close()
    wait_for(fac.out("vandal.txt"))
    fac.write_text(target, fac.read_text(text))


@fac.rule
def vandal(text: fac.OrderOnly = TEXT, target: fac.Output = fac.out("vandal.txt")):
    wait_for(fac.out("reader.started"))
    fac.write_text(text, "damaged")
    fac.write_text(target, "done")
