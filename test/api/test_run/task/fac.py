import sys

import facere as fac


@fac.task(default=True)
def hello():
    assert fac.run(sys.executable, "-c", "print('hello')") == ""
