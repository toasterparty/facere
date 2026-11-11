import os

import facere as fac


@fac.rule(default=True)
def copy(source: fac.Input = "a.txt", copied: fac.Output = fac.out("a.txt")):
    # Stands in for an editor saving a.txt after the build started.
    if os.path.exists("save.txt"):
        os.replace("save.txt", source)
    fac.write_text(copied, fac.read_text(source))
