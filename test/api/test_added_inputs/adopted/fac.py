import facere as fac

GENERATED = []


@fac.rule(default=True)
def compile_(source: fac.Input = "main.c", obj: fac.Output = fac.out("main.o")):
    fac.add_inputs(["include/config.h"])
    fac.write_text(obj, fac.read_text("include/config.h"))


@fac.rule(each=GENERATED, default=True)
def configure(header: fac.Output, spec: fac.Input = "spec.txt"):
    fac.write_text(header, fac.read_text(spec))
