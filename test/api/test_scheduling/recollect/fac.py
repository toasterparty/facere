import facere as fac

PAGES = fac.sources("pages/*.txt")
VERSION = fac.read_text("version.txt")


@fac.rule
def count(pages: list[fac.Input] = PAGES, target: fac.Output = fac.out("count.txt")):
    fac.write_text(target, str(len(pages)))


@fac.rule
def stamp(target: fac.Output = fac.out("version.txt"), version=VERSION):
    fac.write_text(target, version)


@fac.rule
def copy(source: fac.Input = "pages/a.txt", target: fac.Output = fac.out("a.txt")):
    fac.write_text(target, fac.read_text(source))


@fac.task
def add_page():
    fac.write_text("pages/b.txt", "b")


@fac.task
def bump():
    fac.write_text("version.txt", "2")


@fac.task
def edit_page():
    fac.write_text("pages/a.txt", "edited")
