import facere as fac


@fac.rule
def entry(source: fac.Input = "build/a", out: fac.Output = "build/e"):
    pass


@fac.rule
def first(source: fac.Input = "build/b", out: fac.Output = "build/a"):
    pass


@fac.rule
def second(source: fac.Input = "build/a", out: fac.Output = "build/b"):
    pass
