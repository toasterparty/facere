import facere as fac


@fac.rule
def page(out: fac.Output = "build/page.html"):
    pass


@fac.rule
def index(pages=["build/page.html"], out: fac.Output = "build/index.html"):
    pass
