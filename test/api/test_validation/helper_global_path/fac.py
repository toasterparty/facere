import facere as fac

NOTES = "notes.txt"


def read_notes():
    with open(NOTES, encoding="utf-8") as file:
        return file.read()


@fac.rule
def page(target: fac.Output = fac.out("page.txt")):
    with open(target, "w", encoding="utf-8") as file:
        file.write(read_notes())
