import facere_test_words  # noqa: F401 - the import is what this project tests

import facere as fac


@fac.task(default=True)
def nothing():
    pass
