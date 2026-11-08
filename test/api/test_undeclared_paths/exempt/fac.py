import sys

import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    scratch = fac.out("scratch.d")
    fac.write_text(scratch, "scratch")
    fac.run(sys.executable, "-c", "pass", scratch, ".hidden/tool.cfg", "absent.cfg", "-o")
    fac.read_text(scratch)
    fac.read_text(".hidden/tool.cfg")
    fac.write_text("written.txt", "written")
    fac.run(sys.executable, "-c", "pass", "written.txt")
    fac.write_text(result, fac.read_text("written.txt"))
