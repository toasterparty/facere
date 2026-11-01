import os

import facere as fac


@fac.rule(default=True)
def index(pages: fac.Input = "pages", target: fac.Output = fac.out("index.txt")):
    with open(target, "w") as out:
        out.write(" ".join(sorted(os.listdir(pages))))
