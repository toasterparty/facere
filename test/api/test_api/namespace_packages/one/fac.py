from tools.words import WORD

import facere as fac


@fac.task(default=True)
def say():
    print(WORD, flush=True)
