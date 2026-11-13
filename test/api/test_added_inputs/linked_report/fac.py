import facere as fac


# vendor links to real, which the test creates.
@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.add_inputs(["vendor/a.h"])
    fac.write_text(bundled, fac.read_text("vendor/a.h"))
