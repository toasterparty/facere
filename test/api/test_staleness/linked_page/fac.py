import os

import facere as fac


@fac.rule(default=True)
def index(pages: fac.Input = "pages", listing: fac.Output = fac.out("index.txt")):
    names = sorted(os.listdir(pages))
    fac.write_text(listing, " ".join(fac.read_text(f"{pages}/{name}") for name in names))
