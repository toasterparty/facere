import json
import os
import shutil

import facere as fac

DATA = fac.out("data.json")
TOTAL = fac.out("out.txt")


@fac.rule(always=True)
def data(path: fac.Output = DATA):
    fac.fetch.file(path, "https://example.com/data.json")


@fac.rule(default=True)
def sum_(data: fac.Input = DATA, path: fac.Output = TOTAL):
    values = json.loads(fac.read_text(data))
    a, b = values["a"], values["b"]
    assert type(a) is int and type(b) is int, f"a and b must be integers, got {values}"
    fac.write_text(path, f"{a + b}\n")


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
