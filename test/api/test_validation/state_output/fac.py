import facere as fac


@fac.rule
def everything(out: fac.Output = fac.out()):
    pass


@fac.rule
def inside(out: fac.Output = fac.out(".fac/a")):
    pass
