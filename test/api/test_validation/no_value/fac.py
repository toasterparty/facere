import facere as fac


@fac.rule
def copy(source: fac.Input, target: fac.Output = "build/a"):
    pass
