import facere as fac


@fac.rule
def page(source="../notes.txt", out: fac.Output = fac.out("page.txt")):
    with open(out, "w") as file:
        file.write(source)
