import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.add_inputs(["build2/a.h"])
    fac.write_text(bundled, fac.read_text("build2/a.h"))
