import sys

import facere as fac

SCRIPT = "import sys; print('from stdout'); print('from stderr', file=sys.stderr); sys.exit(3)"


@fac.task(default=True)
def fail():
    fac.run(sys.executable, "-c", SCRIPT, quiet=True)
