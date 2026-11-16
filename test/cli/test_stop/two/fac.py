import sys

import facere as fac

SLEEP = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
SLEEP_RULES = [
    {"pid_file": fac.out("a.pid"), "target": fac.out("a.txt")},
    {"pid_file": fac.out("b.pid"), "target": fac.out("b.txt")},
]


@fac.rule(each=SLEEP_RULES, default=True)
def sleep(pid_file: str, target: fac.Output):
    fac.run(sys.executable, "-c", SLEEP, pid_file)
    fac.write_text(target, "done")
