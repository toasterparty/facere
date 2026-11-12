import os

import facere as fac

GENERATED = ["version.h"]
SEARCH = [fac.out("gen"), "include"]


@fac.rule
def generate(folder: fac.Output = fac.out("gen"), names: list[str] = GENERATED):
    os.makedirs(folder, exist_ok=True)
    for name in names:
        fac.write_text(f"{folder}/{name}", "generated")


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
