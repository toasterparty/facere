import os

import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.add_inputs(["a.h"])
    fac.write_text(bundled, fac.read_text("a.h"))
    # Stands in for an editor saving a.h while the recipe still runs.
    if os.path.exists("save.h"):
        os.replace("save.h", "a.h")
