import facere as fac


@fac.rule(default=True)
def forget(target: fac.Output = fac.out("never.txt")):
    pass
