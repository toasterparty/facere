import facere as fac

NOTES = "notes.txt"


@fac.rule
def page(out: fac.Output = "build/a"):
    open(NOTES).read()
