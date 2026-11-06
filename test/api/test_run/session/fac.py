import sys

import facere as fac


@fac.rule(default=True)
def session(target: fac.Output = fac.out("session.txt")):
    leads = fac.run(
        sys.executable, "-c", "import os; print(os.getsid(0) == os.getpid(), end='')", quiet=True
    )
    with open(target, "w") as file:
        file.write(leads)
