import facere as fac


@fac.rule(each=[(fac.out("a"),), (fac.out("b"),)], text="x", default=True)
def write(target: fac.Output, text="", times=2):
    with open(target, "w") as out:
        out.write(text * times)
