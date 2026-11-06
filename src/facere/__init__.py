"""Facere, a build tool configured in plain Python. A fac.py imports it as `import facere as fac`.

The user documentation ships as Markdown in this package's `doc/` directory, beside this file: read `doc/README.md` first, and follow its links in reading order. `fac --help` documents the command line.
"""

from facere._api import (
    Args,
    Input,
    Output,
    env,
    minimum_version,
    out,
    read_text,
    rule,
    sources,
    task,
    write_text,
)
from facere._cli import main
from facere._command import run

__all__ = [
    "Args",
    "Input",
    "Output",
    "env",
    "main",
    "minimum_version",
    "out",
    "read_text",
    "rule",
    "run",
    "sources",
    "task",
    "write_text",
]
