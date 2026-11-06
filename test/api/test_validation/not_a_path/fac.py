import facere as fac


@fac.rule
def copy(source: fac.Input = "", out: fac.Output = "build/a"):
    pass


@fac.rule
def index(pages: list[fac.Input] = "a.md", out: fac.Output = "build/b"):  # ty: ignore[invalid-parameter-default]
    pass


@fac.rule
def write(out: fac.Output = ""):
    pass
