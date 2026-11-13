import facere as fac


def exclaim(text):
    return text + "!"


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt"), style=exclaim):
    fac.write_text(target, style("hi"))
