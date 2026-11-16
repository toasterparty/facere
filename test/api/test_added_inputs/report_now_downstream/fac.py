import facere as fac

READS_HEADER = True
ORDERED_AFTER = [fac.out("gen.h")]
HEADER_SOURCE = "spec.txt"


@fac.rule(default=True)
def compile_(
    order: list[fac.OrderOnly] = ORDERED_AFTER,
    source: fac.Input = "main.c",
    obj: fac.Output = fac.out("main.o"),
):
    if READS_HEADER:
        fac.add_inputs([fac.out("gen.h")])
        fac.write_text(obj, fac.read_text(source) + fac.read_text(fac.out("gen.h")))
    else:
        fac.write_text(obj, fac.read_text(source) + "alone")


@fac.rule(default=True)
def generate(header: fac.Output = fac.out("gen.h"), source: fac.Input = HEADER_SOURCE):
    fac.write_text(header, "from:" + fac.read_text(source))
