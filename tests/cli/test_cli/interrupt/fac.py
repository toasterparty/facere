import sys

import facere as fac

WAIT = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); os.path.exists('block') and time.sleep(60)"


@fac.rule(default=True)
def slow(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.txt")):
    fac.run(sys.executable, "-c", WAIT, fac.out("pid"))
    open(target, "w").close()
