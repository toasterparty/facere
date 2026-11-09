"""Fifteen hundred rules that go stale independently, though one table file is the only thing maintained. It needs nothing but Python, and shows how Facere reports a build with many rules."""

import argparse
import os
import shutil

import facere as fac

ROW_COUNT = 1500
# Read while fac.py loads, and not an input. Each rule receives only its own revision as a value,
# so editing a row makes that row's rule stale and no other.
TABLE = "table.txt"


def read_revisions(table):
    if not os.path.exists(table):
        return [0] * ROW_COUNT
    return [int(line) for line in fac.read_text(table).split()]


ROW_RULES = [
    {"path": fac.out(f"rows/{row:04d}.txt"), "revision": revision}
    for row, revision in enumerate(read_revisions(TABLE))
]


# `fac row` builds all of them, since a name covers every rule its function defines.
@fac.rule(each=ROW_RULES, default=True)
def row(path: fac.Output, revision: int):
    fac.write_text(path, f"revision {revision}\n")


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
