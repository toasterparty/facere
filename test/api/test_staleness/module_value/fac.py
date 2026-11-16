import textutil

import facere as fac


def call(module, text):
    return module.shout(text)


@fac.rule(default=True)
def passed(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, call(textutil, "hi"))


@fac.rule(default=True)
def bound(target: fac.Output = fac.out("b.txt")):
    module = textutil
    fac.write_text(target, module.shout("ho"))
