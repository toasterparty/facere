import sys

import facere as fac

fac.env(FACERE_TEST_SET="project")
fac.env(FACERE_TEST_UNSET=None, FACERE_TEST_OVERRIDDEN="project")


@fac.rule(default=True)
def show(script: fac.Input = "show_env.py", target: fac.Output = fac.out("env.txt")):
    shown = fac.capture(sys.executable, script, env={"FACERE_TEST_OVERRIDDEN": "command"})
    with open(target, "w") as file:
        file.write(shown)
