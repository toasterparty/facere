import os
import time

import facere as fac


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


MEET_RULES = [
    {"tag": "a", "other": "b", "target": fac.out("a.txt")},
    {"tag": "b", "other": "a", "target": fac.out("b.txt")},
]


# Each rule finishes only once the other has started, so they succeed only when executing at once.
@fac.rule(each=MEET_RULES)
def meet(tag, other, target: fac.Output):
    open(fac.out(f"{tag}.started"), "w").close()
    wait_for(fac.out(f"{other}.started"))
    fac.write_text(target, tag)
