import facere as fac

LOOP = []
LOOP.append(LOOP)


@fac.rule
def page(out: fac.Output = "build/a"):
    print(LOOP)
