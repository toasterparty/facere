import sys

import facere as fac


@fac.rule(default=True)
def rule_command(tool: fac.Input = "probe.py", target: fac.Output = fac.out("rule.txt")):
    fac.run(sys.executable, tool, target)
