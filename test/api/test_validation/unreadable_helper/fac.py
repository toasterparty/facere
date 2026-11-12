import os

import facere as fac

namespace = {}
source = "def shout(text):\n    return text.upper()\n"
exec(compile(source, os.path.join(os.path.dirname(__file__), "gone.py"), "exec"), namespace)
shout = namespace["shout"]


@fac.rule
def page(out: fac.Output = "build/a"):
    shout("hi")
