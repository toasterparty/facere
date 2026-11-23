import facere as fac

fac.console(fac.Console.AFTER)
fac.console(fac.Console.ON_FAILURE)


@fac.rule(default=True)
def note(target: fac.Output = fac.out("note.txt")):
    open(target, "w").close()
