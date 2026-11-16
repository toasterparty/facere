import sys

import facere as fac


@fac.rule(terminal=True)
def sign(target: fac.Output = fac.out("signed.txt")):
    fac.run(
        sys.executable,
        "-c",
        "import os, sys; open(sys.argv[1], 'w').write(str(os.isatty(0)))",
        target,
    )
