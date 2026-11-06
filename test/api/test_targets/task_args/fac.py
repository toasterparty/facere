import facere as fac


@fac.rule
def note(target: fac.Output = fac.out("note.txt")):
    open(target, "w").close()


@fac.task
def echo(words: fac.Args):
    print(" ".join(words) or "(none)", flush=True)


@fac.task
def greet(*, words: fac.Args = ("hello",)):
    print(" ".join(words), flush=True)


@fac.task
def silent():
    pass


@fac.task
def hello():
    print("hello", flush=True)
