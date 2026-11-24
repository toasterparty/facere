import sys

import facere as fac


@fac.task(default=True)
def check():
    fac.run(sys.executable, "-c", "print('live')")
    fac.run(sys.executable, "-c", "print('captured')", console=fac.Console.AFTER)
