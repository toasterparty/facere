import facere as fac


@fac.rule
def page(target: fac.Output = fac.out("page.txt")):
    fac.write_text(target, "page")


@fac.task
def show():
    print("shown")
