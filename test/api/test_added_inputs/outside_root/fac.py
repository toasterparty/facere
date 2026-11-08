import os

import facere as fac


@fac.rule(default=True)
def compile_(source: fac.Input = "main.c", obj: fac.Output = fac.out("main.o")):
    fac.add_inputs([os.path.abspath("../gone/stdlib.h"), os.path.abspath("local.h")])
    fac.write_text(obj, fac.read_text(source) + fac.read_text("local.h"))


@fac.rule
def other(obj: fac.Output = fac.out("other.o")):
    fac.write_text(obj, "other")
