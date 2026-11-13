import facere as fac


@fac.rule
def generate(text: fac.Output = fac.out("a.txt")):
    fac.write_text(text, "generated")


# Writes another rule's output, which no rule may do.
@fac.rule
def vandal(text: fac.OrderOnly = fac.out("a.txt"), log: fac.Output = fac.out("log.txt")):
    fac.write_text(text, "damaged")
    fac.write_text(log, "done")


@fac.rule(default=True)
def consume(
    text: fac.Input = fac.out("a.txt"),
    log: fac.Input = fac.out("log.txt"),
    copied: fac.Output = fac.out("copy.txt"),
):
    fac.write_text(copied, fac.read_text(text))
