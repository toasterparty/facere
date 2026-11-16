import os
import time

import facere as fac

FIRST_DONE = fac.out("b.done")


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


# Rewrites its own input, as a formatter run in place does, and finishes last though defined first.
@fac.rule
def tidy_a(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.out")):
    fac.write_text(source, fac.read_text(source) + "!")
    wait_for(FIRST_DONE)
    os.remove(FIRST_DONE)
    fac.write_text(target, "a")


@fac.rule
def tidy_b(source: fac.Input = "b.txt", target: fac.Output = fac.out("b.out")):
    fac.write_text(source, fac.read_text(source) + "!")
    fac.write_text(target, "b")
    open(FIRST_DONE, "w").close()
