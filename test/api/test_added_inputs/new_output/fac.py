import os

import facere as fac

GENERATED = ["version.h"]
HEADERS = [fac.out(f"gen/{name}") for name in GENERATED]
SEARCH = [fac.out("gen"), "include"]


@fac.rule(each=[{"header": header} for header in HEADERS])
def generate(header: fac.Output):
    fac.write_text(header, "generated")


@fac.rule(default=True)
def compile_(
    generated: fac.OrderOnly = fac.out("gen"),
    search: list[str] = SEARCH,
    obj: fac.Output = fac.out("main.o"),
):
    # Stands in for a compiler finding config.h on its include path.
    candidates = [f"{folder}/config.h" for folder in search]
    found = next(path for path in candidates if os.path.exists(path))
    fac.add_inputs([found])
    fac.write_text(obj, fac.read_text(found))
