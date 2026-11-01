import facere as fac


@fac.rule
def first(source: fac.Input = "build/c", out: fac.Output = "build/a"):
    pass


@fac.rule
def second(source: fac.Input = "build/a", out: fac.Output = "build/b"):
    pass


@fac.rule
def third(source: fac.Input = "build/b", out: fac.Output = "build/c"):
    pass
