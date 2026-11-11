import os

import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.write_text("scratch.h", "scratch")
    fac.add_inputs(["scratch.h"])
    os.remove("scratch.h")
    fac.write_text(bundled, "bundled")
