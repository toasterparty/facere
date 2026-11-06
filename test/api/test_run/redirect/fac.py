import sys

import facere as fac


@fac.rule(default=True)
def split(
    script: fac.Input = "write.py",
    out: fac.Output = fac.out("o.txt"),
    err: fac.Output = fac.out("e.txt"),
    both: fac.Output = fac.out("both.txt"),
):
    fac.run(sys.executable, script, stdout=out, stderr=err)
    fac.run(sys.executable, script, stdout=both, stderr=both)


@fac.rule
def err_only(script: fac.Input = "write.py", err: fac.Output = fac.out("err_only.txt")):
    fac.run(sys.executable, script, stderr=err)
