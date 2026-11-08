import facere as fac

GENERATED = fac.out("gen.h")
LISTING = "listing.txt"
HEADERS = [GENERATED]


@fac.rule
def generate(spec: fac.Input = "spec.txt", header: fac.Output = GENERATED):
    fac.write_text(header, fac.read_text(spec))


@fac.rule(default=True)
def compile_(
    listing: fac.Input = LISTING,
    headers: list[fac.OrderOnly] = HEADERS,
    obj: fac.Output = fac.out("main.o"),
):
    names = fac.read_text(listing).split()
    fac.add_inputs(names)
    fac.write_text(obj, fac.read_text(headers[0]) if names else "unused")
