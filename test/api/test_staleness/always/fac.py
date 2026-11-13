import facere as fac

VERSION = fac.out("version.txt")


# Stands in for probing a program's version, which no file Facere tracks shows.
@fac.rule(always=True)
def version(path: fac.Output = VERSION):
    fac.write_text(path, fac.read_text(".tool/version"))


@fac.rule(default=True)
def app(version: fac.Input = VERSION, app: fac.Output = fac.out("app.txt")):
    fac.write_text(app, f"built with {fac.read_text(version)}")
