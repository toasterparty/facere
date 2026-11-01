import facere as fac


@fac.rule
def lower(path: fac.Output = "build/x.txt"):
    open(path, "w").close()


@fac.rule
def upper(path: fac.Output = "build/X.txt"):
    open(path, "w").close()
