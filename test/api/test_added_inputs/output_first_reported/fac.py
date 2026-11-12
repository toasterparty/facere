import os

import facere as fac

GENERATED = fac.out("gen.h")


@fac.rule
def generate(header: fac.Output = GENERATED):
    # Writes the header as the file system's clock ticks, so the rule reading it starts in that tick.
    fac.write_text(header, "generated")
    written_ns = os.stat(header).st_mtime_ns
    while os.stat(header).st_mtime_ns == written_ns:
        fac.write_text(header, "generated")


@fac.rule(default=True)
def compile_(header: fac.OrderOnly = GENERATED, obj: fac.Output = fac.out("main.o")):
    fac.add_inputs([header])
    fac.write_text(obj, fac.read_text(header))
