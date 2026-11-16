import facere as fac


@fac.rule
def broken(target: fac.Output = fac.out("broken.txt")):
    raise RuntimeError("no")


@fac.rule
def fine(target: fac.Output = fac.out("fine.txt")):
    fac.write_text(target, "fine")


@fac.task
def needs_broken(source: fac.Input = fac.out("broken.txt")):
    print("needs_broken ran")


@fac.task
def needs_fine(source: fac.Input = fac.out("fine.txt")):
    print("needs_fine ran")
