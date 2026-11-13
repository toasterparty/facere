import facere as fac


@fac.rule(default=True)
def copy(source: fac.Input = "a.txt", copied: fac.Output = fac.out("a.txt")):
    fac.write_text(copied, fac.read_text(source))
