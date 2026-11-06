import facere as fac

fac.env(LC_ALL="C")
fac.env(LC_ALL="C.UTF-8")


@fac.rule(default=True)
def note(target: fac.Output = fac.out("note.txt")):
    open(target, "w").close()
