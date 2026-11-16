import os
import time

import facere as fac

LOG = fac.out("log.txt")
ONE_AT_A_TIME = fac.pool(1)
STEP_RULES = [{"tag": tag, "target": fac.out(f"step/{tag}.txt")} for tag in ["a", "b", "c"]]
LINK_RULES = [{"tag": tag, "target": fac.out(f"link/{tag}.txt")} for tag in ["a", "b", "c"]]


def count_starts():
    if not os.path.exists(LOG):
        return 0
    return fac.read_text(LOG).count("start")


# Gives another rule a moment to start beside this one, and logs whether one did.
def take_turn(tag):
    with open(LOG, "a") as log:
        log.write(f"start {tag}\n")
    starts = count_starts()
    deadline = time.monotonic() + 0.1
    while count_starts() == starts and time.monotonic() < deadline:
        time.sleep(0.005)
    with open(LOG, "a") as log:
        log.write(f"end {tag}\n")


@fac.rule(each=STEP_RULES)
def step(tag, target: fac.Output):
    take_turn(tag)
    fac.write_text(target, tag)


@fac.rule(each=LINK_RULES, pool=ONE_AT_A_TIME)
def link(tag, target: fac.Output):
    take_turn(tag)
    fac.write_text(target, tag)
