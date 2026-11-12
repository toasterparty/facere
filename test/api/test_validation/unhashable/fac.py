import threading

import facere as fac

LOCK = threading.Lock()


@fac.rule
def page(out: fac.Output = "build/a", lock=LOCK):
    print(LOCK)
