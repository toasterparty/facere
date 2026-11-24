"""Facere, a build tool configured in plain Python. A fac.py imports it as `import facere as fac`.

The user documentation ships as Markdown in this package's `doc/` directory, beside this file: read `doc/README.md` first, and follow its links in reading order. `fac --help` documents the command line.
"""

from facere._api import (
    Args,
    Console,
    FileStore,
    Input,
    OrderOnly,
    Output,
    Store,
    Virtual,
    add_inputs,
    console,
    env,
    epoch,
    give_lock,
    minimum_version,
    out,
    pool,
    read,
    read_text,
    rule,
    sources,
    task,
    write,
    write_text,
)
from facere._cli import main
from facere._command import capture, run

__all__ = [
    "Args",
    "Console",
    "FileStore",
    "Input",
    "OrderOnly",
    "Output",
    "Store",
    "Virtual",
    "add_inputs",
    "capture",
    "console",
    "env",
    "epoch",
    "give_lock",
    "main",
    "minimum_version",
    "out",
    "pool",
    "read",
    "read_text",
    "rule",
    "run",
    "sources",
    "task",
    "write",
    "write_text",
]
