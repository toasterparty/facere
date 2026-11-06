import facere as fac


@fac.rule(default=True)
def index(
    pages: list[fac.Input] = fac.sources("pages/*.md"), target: fac.Output = fac.out("index.txt")
):
    with open(target, "w") as file:
        file.write(" ".join(pages))
