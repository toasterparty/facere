import facere as fac


@fac.rule(default=True)
def tree(sources: fac.Input = ".", archive: fac.Output = fac.out("tree.tar")):
    pass


@fac.rule
def build_dir(everything: fac.OrderOnly = fac.out(), archive: fac.Output = fac.out("build.tar")):
    pass


@fac.rule
def inside(part: fac.Input = fac.out("sub"), archive: fac.Output = fac.out("part.tar")):
    pass


@fac.rule
def make_sub(sub: fac.Output = fac.out("sub")):
    pass


@fac.task
def lint(sources: fac.Input = "."):
    pass
