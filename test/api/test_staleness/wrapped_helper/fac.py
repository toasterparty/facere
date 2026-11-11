import contextlib

import facere as fac


@contextlib.contextmanager
def opened(path):
    with open(path, "w", encoding="utf-8") as file:
        file.write("hi")
        yield file


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    with opened(target) as file:
        file.write("!")
