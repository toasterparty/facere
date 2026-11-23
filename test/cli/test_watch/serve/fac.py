import sys

import facere as fac

SERVE = "import time; time.sleep(60)"


@fac.task
def serve(source: fac.Input = "source.txt"):
    with open(fac.out("starts.txt"), "a", encoding="utf-8") as file:
        file.write(fac.read_text(source))
    fac.run(sys.executable, "-c", SERVE)
