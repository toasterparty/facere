import os

import facere as fac

GENERATED = fac.out("gen")


@fac.rule
def compile_(header: fac.Input = f"{GENERATED}/gen.h", obj: fac.Output = fac.out("main.o")):
    fac.write_text(obj, fac.read_text(header))


@fac.rule
def generate(spec: fac.Input = "spec.txt", folder: fac.Output = GENERATED):
    os.makedirs(folder, exist_ok=True)
    fac.write_text(f"{folder}/gen.h", fac.read_text(spec))
