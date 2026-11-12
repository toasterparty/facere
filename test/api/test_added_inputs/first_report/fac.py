import os
import sys

import facere as fac

# Stands in for a compiler, which reads a.h before the recipe can report that it did.
TOOL = "import sys; open(sys.argv[1], 'w').write(open('a.h').read())"


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.run(sys.executable, "-c", TOOL, bundled)
    if fac.read_text(bundled) == "old":
        # Stands in for an editor saving a.h once the tool has read it.
        fac.write_text(f"{bundled}.save", "new")
        os.replace(f"{bundled}.save", "a.h")
    fac.add_inputs(["a.h"])
