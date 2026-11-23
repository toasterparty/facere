import os
import sys
import time

import facere as fac

HOLD = "import sys, time; open(sys.argv[1], 'w').write('up'); time.sleep(60)"
RECORD = "import sys; open(sys.argv[1], 'w').write('ran')"


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


@fac.rule(default=True)
def hold(target: fac.Output = fac.out("hold.txt")):
    try:
        fac.run(sys.executable, "-c", HOLD, fac.out("hold.started"))
    finally:
        fac.write_text(fac.out("hold.ended"), "ended")
    fac.write_text(target, "done")


# Starts its command only once the interrupt has killed hold's, so Facere refuses it.
@fac.rule(default=True)
def late(target: fac.Output = fac.out("late.txt")):
    fac.write_text(fac.out("late.waiting"), "waiting")
    wait_for(fac.out("hold.ended"))
    fac.run(sys.executable, "-c", RECORD, fac.out("late.ran"))
    fac.write_text(target, "done")
