import facere as fac


@fac.rule(default=True)
def compile_(source: fac.Input = "main.c", obj: fac.Output = fac.out("main.o")):
    fac.add_inputs([source, obj])
    fac.write_text(obj, fac.read_text(source))
