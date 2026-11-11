import facere as fac

MARK = "!"


def exclaim(text, mark=MARK):
    return text + mark


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, exclaim("hi"))
