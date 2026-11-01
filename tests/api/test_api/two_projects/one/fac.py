import facere as fac


@fac.task(default=True)
def one():
    print("one", flush=True)
