import facere as fac


@fac.rule
def positional(*paths, out: fac.Output = "build/a"):
    pass


@fac.rule
def keyword(out: fac.Output = "build/b", **options):
    pass
