import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.add_inputs(["include"])
    fac.write_text(bundled, "bundled")
