from __future__ import annotations

import facere as fac


@fac.rule(default=True)
def copy(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.txt")):
    with open(source) as file, open(target, "w") as out:
        out.write(file.read())
