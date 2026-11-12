import threading

import facere as fac


def exclaim(text, lock=threading.Lock()):
    return text + "!"


@fac.rule
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, exclaim("hi"))
