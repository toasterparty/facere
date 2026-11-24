import facere as fac


@fac.rule
def index(
    pages: list[fac.Input] = fac.sources("pages/*.txt"),
    target: fac.Output = fac.out("index.txt"),
):
    fac.write_text(target, "".join(fac.read_text(page) for page in pages))
