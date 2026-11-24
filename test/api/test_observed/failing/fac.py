import facere as fac


@fac.rule
def half(target: fac.Output = fac.out("half.txt")):
    fac.write_text(target, "half")
    raise RuntimeError("written only half")


@fac.rule
def whole(source: fac.Input = "source.txt", target: fac.Output = fac.out("whole.txt")):
    fac.write_text(target, fac.read_text(source))
