import facere as fac


class Table(fac.FileStore):
    def read(self):
        return dict(line.split("=") for line in fac.read_text(self.path).splitlines())

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{key}={text}\n" for key, text in rows.items()))


TABLE = Table("build/table.txt")
A = fac.Virtual("a", store=TABLE)
B = fac.Virtual("b", store=TABLE)


@fac.rule(output=A, source=B)
def ping(output: fac.Output[fac.Virtual], source: fac.Input[fac.Virtual]):
    fac.write(output, fac.read(source))


@fac.rule(output=B, source=A)
def pong(output: fac.Output[fac.Virtual], source: fac.Input[fac.Virtual]):
    fac.write(output, fac.read(source))
