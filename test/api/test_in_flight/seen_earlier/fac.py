import facere as fac


# Checked first, so the invocation has seen src.txt before `edit` rewrites it.
@fac.rule
def early(source: fac.Input = "src.txt", target: fac.Output = fac.out("early.txt")):
    fac.write_text(target, fac.read_text(source))


# Writes a file it does not declare, as a formatter run in place would.
@fac.rule
def edit(target: fac.Output = fac.out("edit.txt")):
    fac.write_text("src.txt", "edited")
    fac.write_text(target, "done")


@fac.rule(default=True)
def copy(
    source: fac.Input = "src.txt",
    edited: fac.Input = fac.out("edit.txt"),
    early_copy: fac.Input = fac.out("early.txt"),
    target: fac.Output = fac.out("copy.txt"),
):
    fac.write_text(target, fac.read_text(source))
