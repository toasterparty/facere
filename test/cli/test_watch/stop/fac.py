import signal
import sys
import time

import facere as fac


def wait_for_stop():
    # Facere's handler only sets a flag, read where its main thread wakes.
    signum = signal.SIGBREAK if sys.platform == "win32" else signal.SIGTERM
    handler = signal.getsignal(signum)
    deadline = time.monotonic() + 30
    while not getattr(getattr(handler, "__self__", None), "is_stop_requested", False):
        assert time.monotonic() < deadline, "the stop never reached Facere"
        time.sleep(0.005)


@fac.rule
def slow(source: fac.Input = "source.txt", target: fac.Output = fac.out("slow.txt")):
    # Blocks only when told to, so a test picks which cycle a change stops.
    if fac.read_text(source) == "wait\n":
        fac.write_text(fac.out("started"), "started")
        wait_for_stop()
    fac.write_text(target, fac.read_text(source))
