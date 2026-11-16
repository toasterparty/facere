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
"""


def wait_for_stop():
    # Facere's handler runs only once its main thread wakes, while this worker would start `after` at once.
    assert sys.platform == "win32"
    handler = signal.getsignal(signal.SIGBREAK)
    deadline = time.monotonic() + 30
    while not getattr(getattr(handler, "__self__", None), "is_stop_requested", False):
        assert time.monotonic() < deadline, "the stop never reached Facere"
        time.sleep(0.005)


@fac.rule
def slow(target: fac.Output = fac.out("slow.txt")):
    fac.run(sys.executable, "-c", WAIT_FOR_GO, fac.out("pid"))
    wait_for_stop()
    fac.write_text(target, "slow")


@fac.rule(default=True)
def after(source: fac.Input = fac.out("slow.txt"), target: fac.Output = fac.out("after.txt")):
    fac.write_text(target, fac.read_text(source))
