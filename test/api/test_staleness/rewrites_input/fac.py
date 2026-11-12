import facere as fac

SOURCES = ["a.txt", "b.txt"]


# Stands in for a tool that rewrites its own input, as a formatter run in place does.
@fac.rule(each=[{"source": source, "copied": fac.out(source)} for source in SOURCES])
def tidy(source: fac.Input, copied: fac.Output):
    text = fac.read_text(source)
    fac.write_text(source, text)
    fac.write_text(copied, text)
