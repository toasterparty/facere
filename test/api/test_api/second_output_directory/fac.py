import facere as fac

PARSER = fac.out("gen/parser.c")
SOURCES = [*fac.sources("**/*.c"), PARSER]


@fac.rule
def generate(spec: fac.Input = "spec.txt", parser: fac.Output = PARSER):
    fac.write_text(parser, fac.read_text(spec))


@fac.rule
def link(sources: list[fac.Input] = SOURCES, program: fac.Output = fac.out("program")):
    fac.write_text(program, " ".join(fac.read_text(source) for source in sources))
