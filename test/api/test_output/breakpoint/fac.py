import sys

import facere as fac


@fac.rule(default=True)
def debugged(target: fac.Output = fac.out("debugged.txt")):
    print("before")
    value = 42
    breakpoint()
    print("after")
    fac.run(sys.executable, "-c", "print('command')")
    open(target, "w").close()
    assert value


@fac.rule(default=True)
def other(target: fac.Output = fac.out("other.txt")):
    print("other")
    open(target, "w").close()
