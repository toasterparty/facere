import facere as fac


@fac.rule
def a(path: fac.Output = fac.out("a.txt")):
    fac.write_text(path, "a")


@fac.rule
def b(path: fac.Output = fac.out("b.txt")):
    fac.write_text(path, "b")


@fac.task
def hello():
    print("hello")
