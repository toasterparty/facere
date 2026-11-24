import json
import os
import threading
from typing import assert_type

import facere as fac


def misbehave(method):
    if os.path.exists(f"raise-{method}"):
        raise RuntimeError(f"{method} refused")


class Memo:
    """Notes kept as one JSON object in a file, whose methods misbehave where the root holds a file naming them."""

    def __init__(self, path):
        self.path = path

    def stamp(self):
        misbehave("stamp")
        return fac.read_text(self.path) if os.path.exists(self.path) else None

    def read(self, keys):
        misbehave("read")
        held = json.loads(fac.read_text(self.path)) if os.path.exists(self.path) else {}
        if os.path.exists("garble-read"):
            return {key: value.upper() for key, value in held.items()}
        return held

    def update(self, changed):
        misbehave("update")
        if os.path.exists("move-update"):
            self.path = "elsewhere.json"
        held = json.loads(fac.read_text(self.path)) if os.path.exists(self.path) else {}
        if os.path.exists("drop-update"):
            held = {}
        held.update(changed)
        fac.write_text(self.path, json.dumps(held))


MEMO = Memo("memo.json")
NOTES = [fac.Virtual("a", store=MEMO), fac.Virtual("b", store=MEMO)]
NOTE_RULES = [{"output": NOTES[0], "text": "alpha"}, {"output": NOTES[1], "text": "beta"}]


@fac.rule(each=NOTE_RULES, default=True)
def note(output: fac.Output[fac.Virtual], text):
    # ty checks these, so a change to how fac.Input and fac.Output type parameters fails `fac test`.
    assert_type(output, fac.Virtual)
    fac.write(output, text)


@fac.rule(default=True)
def joined(
    notes: list[fac.Input[fac.Virtual]] = NOTES,
    separator: fac.Input = "separator.txt",
    listing: fac.Output = "build/joined.txt",
):
    assert_type(notes, list[fac.Virtual])
    assert_type(separator, str)
    texts = [f"{note.key}={fac.read(note)}" for note in notes]
    fac.write_text(listing, fac.read_text(separator).join(texts))


@fac.rule
def forgetful(output: fac.Output[fac.Virtual] = fac.Virtual("c", store=MEMO)):
    pass


@fac.rule
def unhashable_value(output: fac.Output[fac.Virtual] = fac.Virtual("d", store=MEMO)):
    fac.write(output, threading.Lock())


@fac.rule
def undeclared(listing: fac.Output = "build/undeclared.txt"):
    fac.write_text(listing, fac.read(NOTES[0]))


@fac.task
def peek():
    print(fac.read(NOTES[0]))
