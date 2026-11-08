from helpers_shared import SHOUT

import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.read_text("helpers_shared.py")
    fac.write_text(result, SHOUT)
