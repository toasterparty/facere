import sys

import facere as fac

SLEEP = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"


@fac.rule(default=True)
def quick(target: fac.Output = fac.out("quick.txt")):
    fac.write_text(target, "quick")


# Waits for `quick` to have finished, then blocks until killed.
@fac.rule(default=True)
def slow(quick_file: fac.Input = fac.out("quick.txt"), target: fac.Output = fac.out("slow.txt")):
    fac.run(sys.executable, "-c", SLEEP, fac.out("pid"))
    fac.write_text(target, "slow")
