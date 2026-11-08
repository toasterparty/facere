import facere as fac


@fac.rule(default=True)
def bundle(listing: fac.Input = "listing.txt", bundled: fac.Output = fac.out("bundle.txt")):
    names = fac.read_text(listing).split()
    fac.add_inputs(names)
    fac.write_text(bundled, "".join(fac.read_text(name) for name in names))
