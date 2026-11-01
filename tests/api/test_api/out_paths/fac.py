import facere as fac


@fac.task(default=True)
def show():
    print(
        fac.out("src/a.c", ".o"),
        fac.out("."),
        fac.out("./b"),
        fac.out("build/c.c", ".h"),
        flush=True,
    )
