import sys

import facere as fac


@fac.task(default=True)
def answer():
    stdout = fac.run(sys.executable, "-c", "print(6 * 7)", quiet=True)
    print(f"read {stdout.strip()}")
