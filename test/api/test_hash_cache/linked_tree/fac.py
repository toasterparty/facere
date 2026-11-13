import facere as fac


@fac.rule(default=True)
def stamp(tree: fac.Input = "tree", stamped: fac.Output = fac.out("stamp.txt")):
    fac.write_text(stamped, "stamped")
