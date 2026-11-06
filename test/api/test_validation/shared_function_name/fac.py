import facere as fac


@fac.rule
def docs(out: fac.Output = "build/a"):
    pass


@fac.rule(name="docs")
def manual(out: fac.Output = "build/b"):
    pass
