import sys

import facere as fac


@fac.task
def say():
    fac.run(sys.executable, ["-c", "pass"], "two words")
