import facere as fac

NOTES = "notes.txt"


@fac.task
def show(path=NOTES):
    print(path, NOTES)
