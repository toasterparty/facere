import sys

import facere as fac


@fac.rule(default=True)
def use(entry: str = "tool.cfg", result: fac.Output = fac.out("result.txt")):
    fac.run(sys.executable, "-c", "pass", entry)
    fac.write_text(result, fac.read_text(entry))
