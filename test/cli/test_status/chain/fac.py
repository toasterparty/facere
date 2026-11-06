import facere as fac


@fac.rule
def first(target: fac.Output = fac.out("a.txt")):
    open(target, "w").close()


@fac.rule
def second(source: fac.Input = fac.out("a.txt"), target: fac.Output = fac.out("b.txt")):
    open(target, "w").close()


@fac.task
def between():
    pass
