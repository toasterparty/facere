import sys

import facere as fac


@fac.rule(default=True)
def rule_command(tool: fac.Input = "probe.py", target: fac.Output = fac.out("rule.txt")):
    fac.run(sys.executable, tool, target)


@fac.rule(terminal=True)
def terminal_command(tool: fac.Input = "probe.py", target: fac.Output = fac.out("terminal.txt")):
    fac.run(sys.executable, tool, target)


@fac.task
def task_command(tool: fac.Input = "probe.py"):
    fac.run(sys.executable, tool, fac.out("task.txt"))
