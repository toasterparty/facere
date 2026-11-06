import os

import facere as fac


@fac.rule(default=True)
def site(target: fac.Output = fac.out("site")):
    os.makedirs(target, exist_ok=True)
    with open(f"{target}/index.html", "w") as out:
        out.write("<p>hi</p>")
