import facere as fac


@fac.rule
def one(other: fac.OrderOnly = fac.out("two"), mine: fac.Output = fac.out("one")):
    fac.write_text(mine, "")


@fac.rule
def two(other: fac.Input = fac.out("one"), mine: fac.Output = fac.out("two")):
    fac.write_text(mine, "")
