import facere as fac


@fac.rule(default=True)
def touch(target: fac.Output = fac.out("a")):
    open(target, "w").close()
