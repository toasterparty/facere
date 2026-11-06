import facere as fac


@fac.rule(default=True)
def wrap(source: fac.Input = fac.out("a.txt"), target: fac.Output = fac.out("wrap.txt")):
    with open(source) as file, open(target, "w") as out:
        out.write(f"[{file.read()}]")


@fac.rule(default=True)
def write(target: fac.Output = fac.out("a.txt")):
    with open(target, "w") as out:
        out.write("a")
