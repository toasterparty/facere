import facere as fac

HEADER = fac.out("gen/old.h")


@fac.rule
def generate(spec: fac.Input = "spec.txt", header: fac.Output = HEADER):
    fac.write_text(header, fac.read_text(spec))


@fac.rule
def compile_(header: fac.Input = fac.out("gen/old.h"), obj: fac.Output = fac.out("main.o")):
    fac.write_text(obj, fac.read_text(header))
