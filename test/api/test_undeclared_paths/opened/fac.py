import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.write_text(result, fac.read_text("tool.cfg"))
