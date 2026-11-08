import facere as fac


@fac.rule
def compile_(header: fac.OrderOnly = "absent.h", obj: fac.Output = fac.out("main.o")):
    fac.write_text(obj, "main")
