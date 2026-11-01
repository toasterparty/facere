import facere as fac

LOCK = object()


@fac.rule
def page(out: fac.Output = "build/a", lock=LOCK):
    print(LOCK)
