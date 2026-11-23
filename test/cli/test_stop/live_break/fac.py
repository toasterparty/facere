import signal
import sys
import time

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


def wait_for_stop():
    # Facere's handler runs only once its main thread wakes, so the rule would otherwise finish before the stop.
    assert sys.platform == "win32"
    handler = signal.getsignal(signal.SIGBREAK)
    deadline = time.monotonic() + 30
    while not getattr(getattr(handler, "__self__", None), "is_stop_requested", False):
        assert time.monotonic() < deadline, "the stop never reached Facere"
        time.sleep(0.005)


@fac.rule(default=True)
def slow(target: fac.Output = fac.out("slow.txt")):
    fac.run(sys.executable, "-c", WAIT_FOR_GO, fac.out("pid"), target, console=fac.Console.LIVE)
    wait_for_stop()
