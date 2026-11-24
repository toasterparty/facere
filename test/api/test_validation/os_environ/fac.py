import os

import facere as fac

ENV = os.environ


@fac.rule
def page(out: fac.Output = "build/a"):
    print(ENV["HOME"])
