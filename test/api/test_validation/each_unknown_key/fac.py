import facere as fac


@fac.rule(each=[{"ouput": "build/a"}])
def touch(output: fac.Output):
    open(output, "w").close()
