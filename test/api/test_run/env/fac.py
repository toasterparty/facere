import sys

import facere as fac


@fac.rule(default=True)
def show(script: fac.Input = "show_env.py", target: fac.Output = fac.out("env.txt")):
    shown = fac.run(
        sys.executable,
        script,
        env={"FACERE_TEST_SET": "set", "FACERE_TEST_UNSET": None},
        quiet=True,
    )
    with open(target, "w") as file:
        file.write(shown)
