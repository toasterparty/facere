import facere as fac

fac.env(LC_ALL="C")


@fac.rule(default=True)
def touch(target: fac.Output = fac.out("a.txt")):
    open(target, "w").close()
