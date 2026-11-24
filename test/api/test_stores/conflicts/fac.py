import facere as fac


class Table(fac.FileStore):
    def read(self):
        return dict(line.split("=") for line in fac.read_text(self.path).splitlines())

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{key}={text}\n" for key, text in rows.items()))


TABLE = Table("build/table.txt")
OTHER = Table("build/table.txt")


@fac.rule(output=fac.Virtual("a", store=TABLE))
def first(output: fac.Output[fac.Virtual]):
    fac.write(output, "first")


@fac.rule(output=fac.Virtual("a", store=TABLE))
def second(output: fac.Output[fac.Virtual]):
    fac.write(output, "second")


@fac.rule(rows=[fac.Virtual("z", store=TABLE)])
def reader(rows: list[fac.Input[fac.Virtual]], listing: fac.Output = "build/listing.txt"):
    pass


@fac.rule
def whole(table: fac.Output = "build/table.txt"):
    pass


@fac.rule(output=fac.Virtual("b", store=OTHER))
def other(output: fac.Output[fac.Virtual]):
    fac.write(output, "other")
