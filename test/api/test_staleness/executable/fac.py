import shutil

import facere as fac


@fac.rule(default=True)
def install(script: fac.Input = "tool.sh", installed: fac.Output = fac.out("tool.sh")):
    shutil.copy(script, installed)
