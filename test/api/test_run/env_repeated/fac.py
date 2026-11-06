import sys

import facere as fac

fac.env(LC_ALL="C")
fac.env(LC_ALL="C", TZ="UTC")


@fac.rule(default=True)
def locale(target: fac.Output = fac.out("locale.txt")):
    script = "import os; print(os.environ['LC_ALL'], os.environ['TZ'], end='')"
    fac.run(sys.executable, "-c", script, stdout=target)
