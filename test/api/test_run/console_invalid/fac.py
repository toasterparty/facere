import sys

import facere as fac


@fac.rule(default=True)
def note(target: fac.Output = fac.out("note.txt")):
    fac.run(sys.executable, "-c", "pass", console="live")  # ty: ignore[invalid-argument-type]
