import facere as fac


@fac.rule
def rule_args(words: fac.Args, target: fac.Output = fac.out("a")):
    pass


@fac.task
def two_args(first: fac.Args, second: fac.Args):
    pass


@fac.task(words=("given",))
def filled_args(words: fac.Args):
    pass
