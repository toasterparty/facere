import shutil

import facere as fac


@fac.rule
def copy(source: fac.Input = "a.txt", copied: fac.Output = fac.out("a.txt")):
    fac.write_text(copied, fac.read_text(source))


@fac.task
def tamper(copied: fac.Input = fac.out("a.txt")):
    fac.write_text(copied, "tampered")


@fac.task
def clean():
    shutil.rmtree(fac.out())
