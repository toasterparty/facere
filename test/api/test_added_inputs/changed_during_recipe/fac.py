import facere as fac


@fac.rule(default=True)
def bundle(bundled: fac.Output = fac.out("bundle.txt")):
    fac.add_inputs(["a.h"])
    text = fac.read_text("a.h")
    fac.write_text(bundled, text)
    if text == "edit-me":
        fac.write_text("a.h", "edited")
