import facere as fac


@fac.rule
def generate(src: fac.Input = "src", source: fac.Output = "src/gen.c"):
    fac.write_text(source, "int gen;")
