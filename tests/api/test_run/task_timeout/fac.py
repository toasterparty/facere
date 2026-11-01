import sys

import facere as fac


@fac.task(default=True)
def hang(script: fac.Input = "hang.py"):
    fac.run(sys.executable, script, timeout=1)
