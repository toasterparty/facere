import facere as fac


@fac.rule
def fail(target: fac.Output = fac.out("a.txt")):
    raise RuntimeError("no")


@fac.rule
def after(target: fac.Output = fac.out("b.txt")):
    open(target, "w").close()


@fac.rule
def downstream(source: fac.Input = fac.out("a.txt"), target: fac.Output = fac.out("c.txt")):
    open(target, "w").close()
