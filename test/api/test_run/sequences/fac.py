import sys

import facere as fac

PYTHON = [sys.executable, "-c"]
SCRIPT = "import sys; print(*sys.argv[1:], end='')"


@fac.rule(default=True)
def argv(target: fac.Output = fac.out("argv.txt")):
    shown = fac.run(PYTHON, SCRIPT, ["a", "b"], "c", ("d",), [], quiet=True)
    with open(target, "w") as file:
        file.write(shown)
