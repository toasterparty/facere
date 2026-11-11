import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    names = ["dscp.h", "DSCP.h"]
    fac.add_inputs(names)
    fac.write_text(bundled, " ".join(fac.read_text(name) for name in names))
