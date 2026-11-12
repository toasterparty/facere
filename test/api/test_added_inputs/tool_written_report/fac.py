import sys

import facere as fac

# Stands in for a parser generator that writes its header beside the grammar.
TOOL = "open('parser.h', 'w').write('parser')"


@fac.rule(default=True)
def parser(obj: fac.Output = fac.out("parser.o")):
    fac.run(sys.executable, "-c", TOOL)
    fac.add_inputs(["parser.h"])
    fac.write_text(obj, fac.read_text("parser.h"))
