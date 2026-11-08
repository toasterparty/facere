import sys

import facere as fac


@fac.task
def show():
    fac.run(sys.executable, "-c", "pass", "tool.cfg")
    print(fac.read_text("tool.cfg"))
