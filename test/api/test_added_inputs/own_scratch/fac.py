import facere as fac


@fac.rule(default=True)
def parser(grammar: fac.Input = "grammar.y", obj: fac.Output = fac.out("parser.o")):
    header = f"{obj}.h"
    fac.write_text(header, fac.read_text(grammar).upper())
    fac.add_inputs([header])
    fac.write_text(obj, fac.read_text(header))
