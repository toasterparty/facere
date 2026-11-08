import os

import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.write_text(fac.out("scratch.h"), "scratch")
    fac.add_inputs([fac.out("scratch.h")])
    os.remove(fac.out("scratch.h"))
    fac.write_text(bundled, "bundled")
