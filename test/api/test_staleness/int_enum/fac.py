import enum

import facere as fac


class Level(enum.IntEnum):
    LOW = 1


LEVEL = Level.LOW


@fac.rule(default=True)
def report(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, f"{LEVEL:d}")
