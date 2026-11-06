import facere as fac


@fac.rule(default=True)
def copy(source: fac.Input = "source.txt", target: fac.Output = fac.out("target.txt")):
    fac.write_text(target, fac.read_text(source).upper())
