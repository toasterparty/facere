import os
import sys
import time

import facere as fac

SLEEP = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


@fac.rule
def slow(target: fac.Output = fac.out("slow.txt")):
    fac.write_text(fac.out("started"), "yes")
    wait_for("go")
    fac.write_text(target, "slow")


@fac.rule(default=True)
def after(source: fac.Input = fac.out("slow.txt"), target: fac.Output = fac.out("after.txt")):
    fac.write_text(target, fac.read_text(source))


@fac.task
def serve():
    fac.run(sys.executable, "-c", SLEEP, fac.out("pid"))
    print("the command ended")
