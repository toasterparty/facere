import facere as fac

GENERATED = ["a.h"]
HEADERS = [fac.out(name) for name in GENERATED]


@fac.rule(each=[{"header": header} for header in HEADERS])
def generate(header: fac.Output):
    fac.write_text(header, "generated")


@fac.rule(default=True)
def compile_(headers: list[fac.OrderOnly] = HEADERS, obj: fac.Output = fac.out("main.o")):
    fac.write_text(obj, "compiled")
