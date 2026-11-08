import sys

import facere as fac


@fac.rule(default=True)
def use(config: fac.Input = "tool.cfg", result: fac.Output = fac.out("result.txt")):
    fac.run(sys.executable, "-c", "pass", f"--config={config}", cwd=None)
    fac.write_text(result, fac.read_text(config))
