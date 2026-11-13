import sys

import facere as fac

GENERATED = fac.out("gen.h")
# Stands in for a tool that rewrites a header it read, leaving its content as it was.
TOOL = "import sys; text = open(sys.argv[1]).read(); open(sys.argv[1], 'w').write(text)"


@fac.rule
def generate(header: fac.Output = GENERATED):
    fac.write_text(header, "generated")


@fac.rule(default=True)
def compile_(header: fac.OrderOnly = GENERATED, obj: fac.Output = fac.out("main.o")):
    fac.run(sys.executable, "-c", TOOL, header)
    fac.add_inputs([header])
    fac.write_text(obj, fac.read_text(header))
