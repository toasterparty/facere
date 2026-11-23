import sys

import facere as fac

WAIT_FOR_GO = """
import os, sys, time
with open(sys.argv[1], "w") as file:
    file.write(str(os.getpid()))
deadline = time.monotonic() + 30
while not os.path.exists("go"):
    assert time.monotonic() < deadline, "go never appeared"
    time.sleep(0.005)
with open(sys.argv[2], "w") as file:
    file.write("slow")
"""


@fac.rule(default=True)
def slow(target: fac.Output = fac.out("slow.txt")):
    fac.run(sys.executable, "-c", WAIT_FOR_GO, fac.out("pid"), target, console=fac.Console.LIVE)
