import sys

import facere as fac


@fac.rule(default=True)
def feed(
    script: fac.Input = "cat.py",
    source: fac.Input = "in.txt",
    target: fac.Output = fac.out("fed.txt"),
):
    unfed = fac.run(sys.executable, script, quiet=True)
    fed = fac.run(sys.executable, script, stdin=source, quiet=True)
    with open(target, "w") as file:
        file.write(f"{unfed!r} {fed!r}")
