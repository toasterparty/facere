import facere as fac


@fac.rule
def compile_(obj: fac.Output = fac.out("main.o")):
    fac.write_text(obj, "main")


@fac.task
def check(obj: fac.OrderOnly = fac.out("main.o")):
    pass
