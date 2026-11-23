import sys

import facere as fac


@fac.rule(default=True)
def echo(script: fac.Input = "echo.py", target: fac.Output = fac.out("echo.txt")):
    fac.run(sys.executable, script, "0")
    open(target, "w").close()


@fac.rule
def quiet_echo(script: fac.Input = "echo.py", target: fac.Output = fac.out("quiet.txt")):
    fac.run(sys.executable, script, "0", console=fac.Console.ON_FAILURE)
    open(target, "w").close()


@fac.rule
def failing_echo(script: fac.Input = "echo.py", target: fac.Output = fac.out("failing.txt")):
    fac.run(sys.executable, script, "3", console=fac.Console.ON_FAILURE)
    open(target, "w").close()
