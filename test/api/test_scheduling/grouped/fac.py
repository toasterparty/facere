import os
import sys
import time

import facere as fac

SAY_RULES = [
    {"tag": "a", "other": "b", "target": fac.out("a.txt")},
    {"tag": "b", "other": "a", "target": fac.out("b.txt")},
]


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


# Each rule prints, waits for the other to have printed, then runs a command that prints.
@fac.rule(each=SAY_RULES)
def say(tag, other, target: fac.Output):
    print(f"{tag} 1")
    open(fac.out(f"{tag}.said"), "w").close()
    wait_for(fac.out(f"{other}.said"))
    fac.run(sys.executable, "-c", f"print('{tag} 2')")
    print(f"{tag} 3", file=sys.stderr)
    fac.write_text(target, tag)
