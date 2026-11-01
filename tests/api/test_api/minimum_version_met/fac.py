import facere as fac

fac.minimum_version("0.1")
fac.minimum_version("0.1.0")


@fac.task(default=True)
def nothing():
    pass
