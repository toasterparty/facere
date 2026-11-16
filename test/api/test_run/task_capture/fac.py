import sys

import facere as fac


@fac.task(default=True)
def answer():
    stdout = fac.capture(sys.executable, "-c", "print(6 * 7)")
    print(f"read {stdout.strip()}")
