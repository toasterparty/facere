import facere as fac


@fac.rule(default=True)
def log(source: fac.Input = "a.txt", target: fac.Output = fac.out("log.txt")):
    with open(source) as file, open(target, "a") as out:
        out.write(file.read())
