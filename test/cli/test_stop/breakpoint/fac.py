import os
import time

import facere as fac


@fac.rule(default=True)
def debugged(held: str = fac.out("held"), target: fac.Output = fac.out("debugged.txt")):
    print("before")
    open(held, "w").close()
    breakpoint()
    open(target, "w").close()


@fac.rule(default=True)
def other(
    held: str = fac.out("held"),
    done: str = fac.out("other-done"),
    target: fac.Output = fac.out("other.txt"),
):
    deadline = time.monotonic() + 30
    while not os.path.exists(held):
        assert time.monotonic() < deadline, "debugged never reached its breakpoint"
        time.sleep(0.01)
    print("other")
    open(target, "w").close()
    with open(done, "w") as file:
        file.write("done")
