import facere as fac


@fac.task(default=True)
def hello():
    print("hello", flush=True)
