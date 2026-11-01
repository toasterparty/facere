import facere as fac


@fac.rule(default=True)
def missing(target: fac.Output = fac.out("never.txt")):
    fac.run("facere-no-such-program", "--help")
