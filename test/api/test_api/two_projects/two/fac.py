import facere as fac


@fac.task(default=True)
def two():
    print("two", flush=True)
