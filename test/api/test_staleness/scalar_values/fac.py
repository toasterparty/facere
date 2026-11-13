import facere as fac

SCALE = 1.5
MARK = b"!"


@fac.rule(default=True)
def shout(target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, f"{SCALE}{MARK.decode()}")
