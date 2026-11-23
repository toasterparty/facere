import lib

import facere as fac

GREETING = fac.read_text("greeting.txt")


@fac.rule
def app(sources: list[fac.Input] = fac.sources("src/*.c"), target: fac.Output = fac.out("app")):
    fac.write_text(target, lib.join([fac.read_text(source) for source in sources]))


@fac.task
def serve(
    app: fac.Input = fac.out("app"), site: fac.Input = "site", notes: fac.Input = "notes.txt"
):
    print(GREETING)
