import facere as fac


def touch(target: fac.Output = fac.out("a")):
    open(target, "w").close()


def show():
    pass


assert fac.rule(touch) is touch
assert fac.rule(name="other", target=fac.out("b"))(touch) is touch
assert fac.task(show) is show
assert fac.task(name="shown")(show) is show
