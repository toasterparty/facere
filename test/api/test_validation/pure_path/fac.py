from pathlib import PurePosixPath

import facere as fac


@fac.rule
def page(out: fac.Output = "build/a", directory=PurePosixPath("docs")):
    pass
