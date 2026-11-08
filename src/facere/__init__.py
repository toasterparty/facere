"""Facere, a build tool configured in plain Python. A fac.py imports it as `import facere as fac`.

The user documentation ships as Markdown in this package's `doc/` directory, beside this file: read `doc/README.md` first, and follow its links in reading order. `fac --help` documents the command line.
"""

import importlib
from types import ModuleType
from typing import TYPE_CHECKING

from facere._api import (
    Args,
    Input,
    OrderOnly,
    Output,
    add_inputs,
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

if TYPE_CHECKING:
    from facere import c

__all__ = [
    "Args",
    "Input",
    "OrderOnly",
    "Output",
    "add_inputs",
    "c",
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


def __getattr__(name: str) -> ModuleType:
    if name == "c":
        return importlib.import_module("facere.c")
    raise AttributeError(f"module 'facere' has no attribute {name!r}")
