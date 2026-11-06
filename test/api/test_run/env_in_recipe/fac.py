import facere as fac


@fac.task(default=True)
def late():
    fac.env(LC_ALL="C")
