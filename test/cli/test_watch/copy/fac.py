import facere as fac


@fac.rule
def copy(
    source: fac.Input = "source.txt",
    other: fac.Input = "other.txt",
    target: fac.Output = fac.out("copy.txt"),
):
    fac.write_text(target, fac.read_text(source) + fac.read_text(other))
