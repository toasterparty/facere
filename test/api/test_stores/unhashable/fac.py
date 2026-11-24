import threading
from typing import Any

import facere as fac


class Locked:
    """A store holding a lock, which Facere can't hash."""

    def __init__(self):
        self.lock = threading.Lock()

    def stamp(self):
        return None

    def read(self, keys):
        return {}

    def update(self, changed):
        pass


class Unwritable:
    def stamp(self):
        return None

    def read(self, keys):
        return {}


class Notes:
    def stamp(self):
        return None

    def read(self, keys):
        return {}

    def update(self, changed):
        pass


NOTES = Notes()
# Typed as Any, since a type checker already rejects a store missing a method.
UNWRITABLE: Any = Unwritable()


@fac.rule(output=fac.Virtual("a", store=Locked()))
def locked_store(output: fac.Output[fac.Virtual]):
    pass


@fac.rule(output=fac.Virtual("a", store=UNWRITABLE))
def unwritable_store(output: fac.Output[fac.Virtual]):
    pass


@fac.rule(output=fac.Virtual(["a"], store=NOTES))
def list_key(output: fac.Output[fac.Virtual]):
    pass


@fac.rule(output=fac.Virtual(threading.Lock(), store=NOTES))
def lock_key(output: fac.Output[fac.Virtual]):
    pass
