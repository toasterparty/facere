import facere as fac

SOURCES = fac.sources("**/*.c", "*.txt", "src/.dir/*.c", "*.txt")


@fac.task(default=True)
def show(files: list[fac.Input] = SOURCES):
    print(files, flush=True)
