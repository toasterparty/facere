import sys

import facere as fac


@fac.task(default=True)
def slow():
    fac.run(sys.executable, "-c", "pass", timeout=1)
