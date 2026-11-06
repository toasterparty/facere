import other.fac  # noqa: F401 - the import is what this project tests

import facere as fac


@fac.task(default=True)
def nothing():
    pass
