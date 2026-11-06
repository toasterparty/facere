import facere as fac

shout = lambda text: text.upper()  # noqa: E731


@fac.rule
def page(out: fac.Output = "build/a"):
    shout("hi")
