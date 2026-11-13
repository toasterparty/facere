import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.add_inputs([".sdk/a.h"])
    fac.write_text(bundled, fac.read_text(".sdk/a.h"))
