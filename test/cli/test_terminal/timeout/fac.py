import sys

import facere as fac

HANG = "import sys, time; print('stuck here', file=sys.stderr, flush=True); time.sleep(60)"


@fac.rule(default=True)
def hang(target: fac.Output = fac.out("hang.txt")):
    fac.run(sys.executable, "-c", HANG, timeout=1)
    fac.write_text(target, "done")
