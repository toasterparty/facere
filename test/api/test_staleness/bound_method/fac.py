import facere as fac

GREET = "Hello, {}!".format


@fac.rule(default=True)
def greet(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, GREET("you"))
