import os

import facere as fac


@fac.rule(default=True)
def listing(src: fac.Input = "src", target: fac.Output = fac.out("listing.txt")):
    fac.add_inputs(["src/gen.c"])
    fac.write_text(target, " ".join(sorted(os.listdir(src))))


@fac.rule
def generate(source: fac.Output = "src/gen.c"):
    fac.write_text(source, "int gen;")
