import facere as fac


@fac.rule(default=True)
def touch(target: fac.Output = fac.out("x.txt")):
    open(target, "w").close()
