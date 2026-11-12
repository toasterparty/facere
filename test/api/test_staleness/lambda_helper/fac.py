import facere as fac

shout = lambda text: text.upper() + "!"  # noqa: E731


@fac.rule(default=True)
def page(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, shout("hi"))
