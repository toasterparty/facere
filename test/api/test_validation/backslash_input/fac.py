import facere as fac


@fac.rule
def first(out: fac.Output = fac.out("a.txt")):
    with open(out, "w") as file:
        file.write("a")


@fac.rule(default=True)
def second(source: fac.Input = "build\\a.txt", out: fac.Output = fac.out("b.txt")):
    with open(source) as file, open(out, "w") as target:
        target.write(file.read())
