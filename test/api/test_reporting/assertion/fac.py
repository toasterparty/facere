import facere as fac


@fac.rule(default=True)
def check(target: fac.Output = fac.out("checked.txt")):
    assert 1 + 1 == 3, "arithmetic"
