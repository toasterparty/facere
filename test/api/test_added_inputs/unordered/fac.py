import os

import facere as fac

GENERATED = fac.out("gen/gen.h")


@fac.rule
def generate(folder: fac.Output = fac.out("gen")):
    os.makedirs(folder, exist_ok=True)
    fac.write_text(GENERATED, "gen")


@fac.rule(default=True)
def compile_(early: fac.Input = fac.out("gen"), obj: fac.Output = fac.out("main.o")):
    fac.add_inputs([GENERATED])
    fac.write_text(obj, "main")


@fac.rule
def racing(obj: fac.Output = fac.out("racing.o")):
    fac.add_inputs([GENERATED])
    fac.write_text(obj, "racing")
