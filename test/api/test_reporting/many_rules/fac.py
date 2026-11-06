import facere as fac


@fac.rule(each=[{"target": fac.out(f"{n}.txt")} for n in range(20)], default=True)
def touch(target: fac.Output):
    open(target, "w").close()
