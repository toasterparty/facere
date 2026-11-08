import sys

import facere as fac

TOOL = """
import sys
names, depfile = open(sys.argv[1]).read().split(), sys.argv[2]
open(depfile, "w").write("\\n".join(names))
open(sys.argv[3], "w").write("".join(open(name).read() for name in names))
"""


@fac.rule(default=True)
def bundle(listing: fac.Input = "listing.txt", bundled: fac.Output = fac.out("bundle.txt")):
    depfile = f"{bundled}.d"
    fac.run(sys.executable, "-c", TOOL, listing, depfile, bundled)
    fac.add_inputs(fac.read_text(depfile).split())
