import sys

import facere as fac


@fac.rule(default=True)
def hang(script: fac.Input = "hang.py", target: fac.Output = fac.out("never.txt")):
    fac.run(sys.executable, script, timeout=2)
