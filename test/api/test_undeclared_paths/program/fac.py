import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.run("tools/run.py", stdout=result)
