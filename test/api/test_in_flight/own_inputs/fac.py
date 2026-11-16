import os
import time

import facere as fac

READ_RULES = [
    {"tag": "a", "other": "b", "source": "a.txt", "target": fac.out("a.txt")},
    {"tag": "b", "other": "a", "source": "b.txt", "target": fac.out("b.txt")},
]


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


# Each rule opens its own input only once both are executing.
@fac.rule(each=READ_RULES)
def read(tag, other, source: fac.Input, target: fac.Output):
    open(fac.out(f"{tag}.started"), "w").close()
    wait_for(fac.out(f"{other}.started"))
    fac.write_text(target, fac.read_text(source))
