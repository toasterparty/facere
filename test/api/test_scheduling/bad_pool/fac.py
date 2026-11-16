import facere as fac


@fac.rule(pool=2)  # ty: ignore[invalid-argument-type]
def link(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, "a")
