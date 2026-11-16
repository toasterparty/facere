import textutil

import facere as fac

TOOLS = (textutil,)


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, TOOLS[0].shout("hi"))
