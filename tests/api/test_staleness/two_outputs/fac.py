import facere as fac


@fac.rule(each=[(fac.out("x"), fac.out("y"))], default=True)
def write(first: fac.Output, second: fac.Output):
    open(first, "w").write("first")
    open(second, "w").write("second")
