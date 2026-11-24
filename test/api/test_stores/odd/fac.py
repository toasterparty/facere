import json
import os
import threading

import facere as fac


class Odd:
    """Values kept as one JSON object in a file, whose methods misbehave where the root holds a file naming how."""

    def __init__(self, path):
        self.path = path

    def stamp(self):
        return threading.Lock() if os.path.exists("lock-stamp") else None

    def read(self, keys):
        held = json.loads(fac.read_text(self.path)) if os.path.exists(self.path) else {}
        if os.path.exists("empty-read"):
            return {}
        if os.path.exists("list-read"):
            return list(held)
        if os.path.exists("lock-read"):
            return {key: threading.Lock() for key in held}
        return held

    def update(self, changed):
        if os.path.exists("raise-update"):
            raise RuntimeError("update refused")
        held = json.loads(fac.read_text(self.path)) if os.path.exists(self.path) else {}
        fac.write_text(self.path, json.dumps({**held, **changed}))


class Table(fac.FileStore):
    def read(self):
        return dict(line.split("=") for line in fac.read_text(self.path).splitlines())

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{key}={text}\n" for key, text in rows.items()))


@fac.rule(default=True)
def pair(
    note: fac.Output[fac.Virtual] = fac.Virtual("a", store=Odd("odd.json")),
    row: fac.Output[fac.Virtual] = fac.Virtual("a", store=Table(fac.out("table.txt"))),
):
    fac.write(note, "alpha")
    fac.write(row, "alpha")


@fac.rule
def summary(
    note: fac.Output[fac.Virtual] = fac.Virtual("b", store=Odd("odd.json")),
    listing: fac.Output = fac.out("summary.txt"),
):
    fac.write(note, "beta")
    fac.write_text(listing, "beta")


@fac.task
def publish(listing: fac.Input = fac.out("summary.txt")):
    print(f"published {fac.read_text(listing)}")
