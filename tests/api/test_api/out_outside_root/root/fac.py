import facere as fac


@fac.task(default=True)
def show():
    print(fac.out("a"), fac.out(fac.out("a")), flush=True)
