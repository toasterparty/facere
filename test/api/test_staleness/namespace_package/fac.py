import tools.textutil

import facere as fac


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, tools.textutil.shout("hi"))
