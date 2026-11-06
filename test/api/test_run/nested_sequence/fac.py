import facere as fac


@fac.rule(default=True)
def nested(target: fac.Output = fac.out("never.txt")):
    fac.run("python", [["-V"]])  # ty: ignore[invalid-argument-type]
