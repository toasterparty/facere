import facere as fac

SUFFIX = "!"
UNREAD = 1


@fac.rule(default=True)
def shout(source: fac.Input = "a.txt", target: fac.Output = fac.out("a.txt"), times=1):
    with open(source, encoding="utf-8") as file:
        text = file.read()
    with open(target, "w", encoding="utf-8") as file:
        file.write(text.upper() * times + SUFFIX)


@fac.task
def show(path: fac.Input = fac.out("a.txt")):
    print(open(path).read(), flush=True)
