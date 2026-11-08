import facere as fac


@fac.rule
def make(made: fac.Output = fac.out("made.txt")):
    fac.write_text(made, "made")


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.write_text(result, fac.read_text(fac.out("made.txt")))
