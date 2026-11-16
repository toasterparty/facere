import os
import sys
import time

import facere as fac

# Each invocation that loads this file says so, as soon as it loads it.
with open("loads.txt", "a") as loads:
    loads.write("loaded\n")


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


@fac.rule(default=True)
def slow(target: fac.Output = fac.out("slow.txt")):
    fac.write_text(fac.out("holding"), "yes")
    wait_for("go")
    fac.write_text(target, "done")


@fac.rule
def quick(target: fac.Output = fac.out("quick.txt")):
    fac.write_text(target, "quick")


@fac.task
def nested():
    fac.run(sys.executable, "-m", "facere", "quick")


@fac.task
def nested_elsewhere():
    fac.run(sys.executable, "-m", "facere", "--out", "build2", "quick")
