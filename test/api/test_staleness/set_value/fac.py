import facere as fac


@fac.rule(default=True, marks={"!"})
def shout(marks, target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, repr(marks))
