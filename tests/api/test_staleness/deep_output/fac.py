import facere as fac


@fac.rule(default=True)
def deep(target: fac.Output = fac.out("a/b/c.txt")):
    open(target, "w").close()
