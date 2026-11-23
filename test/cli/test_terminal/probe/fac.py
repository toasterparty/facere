import sys

import facere as fac


@fac.rule(default=True)
def rule_command(tool: fac.Input = "probe.py", target: fac.Output = fac.out("rule.txt")):
    fac.run(sys.executable, tool, target)


@fac.rule
def live_command(tool: fac.Input = "probe.py", target: fac.Output = fac.out("live.txt")):
    fac.run(sys.executable, tool, target, console=fac.Console.LIVE)


@fac.task
def task_command(tool: fac.Input = "probe.py"):
    fac.run(sys.executable, tool, fac.out("task.txt"))


@fac.rule
def ordered(target: fac.Output = fac.out("ordered.txt")):
    print("printed before")
    fac.run(sys.executable, "-c", "print('shown live')", console=fac.Console.LIVE)
    print("printed after")
    open(target, "w").close()
