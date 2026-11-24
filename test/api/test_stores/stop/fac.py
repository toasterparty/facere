import os
import time

import facere as fac


class Table(fac.FileStore):
    def read(self):
        return dict(line.split("=") for line in fac.read_text(self.path).splitlines())

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{key}={text}\n" for key, text in rows.items()))


TABLE = Table(fac.out("table.txt"))
FIRST = fac.Virtual("a", store=TABLE)


def wait_for(path):
    deadline = time.monotonic() + 30
    while not os.path.exists(path):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.005)


@fac.rule(default=True)
def first(output: fac.Output[fac.Virtual] = FIRST):
    fac.write(output, "alpha")


@fac.rule(default=True)
def slow(source: fac.Input[fac.Virtual] = FIRST, listing: fac.Output = fac.out("listing.txt")):
    fac.write_text(fac.out("started"), "yes")
    wait_for("go")
    fac.write_text(listing, fac.read(source))


@fac.rule(default=True)
def last(
    listing: fac.Input = fac.out("listing.txt"),
    output: fac.Output[fac.Virtual] = fac.Virtual("b", store=TABLE),
):
    fac.write(output, fac.read_text(listing))
