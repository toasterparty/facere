import sys

import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.run(sys.executable, "-c", "pass", "tool.cfg", cwd=None)
    fac.write_text(result, "done")
