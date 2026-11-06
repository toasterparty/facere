import facere as fac


@fac.rule(default=True)
def page(out: fac.Output = fac.out("page.txt"), depfile=fac.out("page.d")):
    with open(depfile, "w") as file:
        file.write("page.txt:")
    with open(out, "w") as file:
        file.write("page")
