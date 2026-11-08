import facere as fac


@fac.rule(default=True)
def use(result: fac.Output = fac.out("result.txt")):
    fac.add_inputs(["tool.cfg"])
    fac.write_text(result, fac.read_text("tool.cfg"))
