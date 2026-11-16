import sys

import facere as fac


@fac.rule(default=True)
def feed(
    script: fac.Input = "cat.py",
    source: fac.Input = "in.txt",
    target: fac.Output = fac.out("fed.txt"),
):
    unfed = fac.capture(sys.executable, script)
    fed = fac.capture(sys.executable, script, stdin=source)
    with open(target, "w") as file:
        file.write(f"{unfed!r} {fed!r}")
