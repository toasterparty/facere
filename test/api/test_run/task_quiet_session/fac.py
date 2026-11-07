import sys

import facere as fac

LEADS_SESSION = "import os; print(os.getsid(0) == os.getpid(), end='')"


@fac.task(default=True)
def session():
    print(fac.run(sys.executable, "-c", LEADS_SESSION, quiet=True))
