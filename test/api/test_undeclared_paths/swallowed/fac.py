import contextlib

import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    with contextlib.suppress(Exception):
        fac.read_text("tool.cfg")
    fac.write_text(result, "done")
