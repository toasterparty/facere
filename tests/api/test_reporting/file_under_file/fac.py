import facere as fac


@fac.rule
def file(target: fac.Output = fac.out("x")):
    open(target, "w").close()


@fac.rule
def nested(target: fac.Output = fac.out("x/y")):
    open(target, "w").close()
