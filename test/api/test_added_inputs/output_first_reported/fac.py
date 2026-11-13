import facere as fac

GENERATED = fac.out("gen.h")


@fac.rule
def generate(header: fac.Output = GENERATED):
    fac.write_text(header, "generated")


@fac.rule(default=True)
def compile_(header: fac.OrderOnly = GENERATED, obj: fac.Output = fac.out("main.o")):
    fac.add_inputs([header])
    fac.write_text(obj, fac.read_text(header))
