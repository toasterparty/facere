import facere as fac


@fac.rule(each=[{"first": fac.out("x"), "second": fac.out("y")}], default=True)
def write(first: fac.Output, second: fac.Output):
    open(first, "w").write("first")
    open(second, "w").write("second")
