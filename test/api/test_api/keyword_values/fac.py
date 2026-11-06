import facere as fac


@fac.rule(each=[{"target": fac.out("a")}, {"target": fac.out("b")}], text="x", default=True)
def write(target: fac.Output, text="", times=2):
    with open(target, "w") as out:
        out.write(text * times)
