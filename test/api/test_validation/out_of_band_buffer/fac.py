import pickle

import facere as fac


def reduce_buffered(buffered, protocol):
    if protocol >= 5:
        return Buffered, (pickle.PickleBuffer(buffered.data),)
    return Buffered, (bytes(buffered.data),)


class Buffered:
    """Reduces to an out-of-band buffer from protocol 5, as a numpy array does."""

    def __init__(self, data):
        self.data = data

    __reduce_ex__ = reduce_buffered


@fac.rule
def page(out: fac.Output = "build/a", table: object = Buffered(b"table")):
    with open(out, "w") as file:
        file.write("written")
