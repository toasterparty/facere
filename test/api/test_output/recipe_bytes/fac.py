import sys

import facere as fac


@fac.rule
def page(target: fac.Output = fac.out("page.txt")):
    print("before")
    sys.stdout.buffer.write(b"caf\xc3\xa9\n")
    print("after")
    fac.write_text(target, "page")


@fac.task
def show():
    print("before")
    sys.stdout.buffer.write(b"caf\xc3\xa9\n")
    print("after")
