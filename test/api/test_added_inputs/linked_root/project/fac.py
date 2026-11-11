import os

import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    # Stands in for a tool whose depfile lists resolved paths.
    fac.add_inputs([os.path.realpath("a.h")])
    fac.write_text(bundled, fac.read_text("a.h"))
