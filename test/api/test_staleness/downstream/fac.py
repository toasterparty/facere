import facere as fac


@fac.rule
def copy(source: fac.Input = "a.txt", target: fac.Output = fac.out("copy.txt")):
    with open(source) as file, open(target, "w") as out:
        out.write(file.read())


@fac.rule(default=True)
def wrap(source: fac.Input = fac.out("copy.txt"), target: fac.Output = fac.out("wrap.txt")):
    with open(source) as file, open(target, "w") as out:
        out.write(f"[{file.read()}]")
