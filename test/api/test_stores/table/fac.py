import facere as fac


class Table(fac.FileStore):
    """One `key=text` line per row, which a line without `=` makes unreadable."""

    def read(self):
        rows = {}
        for line in fac.read_text(self.path).splitlines():
            key, text = line.split("=")
            rows[key] = text
        return rows

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{key}={text}\n" for key, text in rows.items()))


TABLE = Table(fac.out("table.txt"))
ROW_RULES = [
    {"output": fac.Virtual("a", store=TABLE), "text": "alpha"},
    {"output": fac.Virtual("b", store=TABLE), "text": "beta"},
]


@fac.rule(each=ROW_RULES, default=True)
def row(output: fac.Output[fac.Virtual], text):
    fac.write(output, text)


@fac.rule
def peek(listing: fac.Output = fac.out("peek.txt")):
    fac.write_text(listing, fac.read_text(fac.out("table.txt")))


@fac.rule
def shout(table: fac.Input = fac.out("table.txt"), output: fac.Output = fac.out("shout.txt")):
    fac.write_text(output, fac.read_text(table).upper())


@fac.rule
def route(page: fac.Output = fac.out("app/[slug]")):
    fac.write_text(page, "slug")
