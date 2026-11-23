import facere as fac


@fac.rule(default=True)
def note(pipe: fac.Input = "pipe", target: fac.Output = fac.out("note.txt")):
    fac.write_text(target, "noted")
