import facere as fac


@fac.rule(each=[("build/a",), ["build/b"]])  # ty: ignore[invalid-argument-type]
def touch(out: fac.Output):
    open(out, "w").close()
