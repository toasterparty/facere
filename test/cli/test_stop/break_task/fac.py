import sys

import facere as fac

IGNORE_BREAK = """
import os, signal, sys, time
assert sys.platform == "win32"
signal.signal(signal.SIGBREAK, signal.SIG_IGN)
with open(sys.argv[1], "w") as file:
    file.write(str(os.getpid()))
time.sleep(60)
"""


@fac.task
def serve():
    fac.run(sys.executable, "-c", IGNORE_BREAK, fac.out("pid"))
