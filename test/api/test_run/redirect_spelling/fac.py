import sys

import facere as fac


@fac.rule(default=True)
def both(script: fac.Input = "write.py", out: fac.Output = fac.out("both.txt")):
    fac.run(sys.executable, script, stdout=out, stderr=f"./{out}")
