import facere as fac

HEADER = fac.out("gen/config.h")


@fac.rule
def generate(header: fac.Output = HEADER):
    fac.write_text(header, "generated")


@fac.rule(default=True)
def compile_(header: fac.OrderOnly = HEADER, obj: fac.Output = fac.out("main.o")):
    fac.add_inputs([header])
    fac.write_text(obj, fac.read_text(header))
