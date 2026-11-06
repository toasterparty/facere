"""Fifteen hundred rules that go stale independently, each writing one row of a single output file."""

import argparse
import os
import shutil

import facere as fac

ROW_COUNT = 1500
TABLE = "table.txt"


def read_revisions(table):
    if not os.path.exists(table):
        return [0] * ROW_COUNT
    return [int(line) for line in fac.read_text(table).split()]


class Rows(fac.FileStore):
    """One `NNNN text` line per row."""

    def read(self):
        rows = {}
        for line in fac.read_text(self.path).splitlines():
            row, _, text = line.partition(" ")
            rows[int(row)] = text
        return rows

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{row:04d} {text}\n" for row, text in rows.items()))


ROWS = Rows(fac.out("rows.txt"))
ROW_RULES = [
    {"output": fac.Virtual(ROWS, row), "revision": revision}
    for row, revision in enumerate(read_revisions(TABLE))
]


@fac.rule(each=ROW_RULES, default=True)
def row(output: fac.VirtualOutput, revision: int):
    fac.write(output, f"revision {revision}")


@fac.task
def invalidate(args: fac.Args, table: str = TABLE):
    """Raise the revision of the first --count rows in the table, all of them by default, so their rules go stale."""
    parser = argparse.ArgumentParser(prog="fac invalidate --")
    parser.add_argument("--count", type=int, default=ROW_COUNT)
    count = parser.parse_args(args).count
    revisions = read_revisions(table)
    for index in range(min(count, len(revisions))):
        revisions[index] += 1
    fac.write_text(table, "".join(f"{revision}\n" for revision in revisions))


@fac.task
def clean():
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
