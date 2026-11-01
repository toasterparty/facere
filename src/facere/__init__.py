"""Facere, a build tool configured in plain Python. A fac.py imports it as `import facere as fac`.

The user documentation ships as Markdown in this package's `doc/` directory, beside this file: read `doc/getting-started.md` first, then `doc/best-practices.md` before writing rules for a real project, and `doc/terminology.md` for any unfamiliar term.
"""

from facere._api import Input, Output, minimum_version, out, rule, task
from facere._cli import main
from facere._command import run

__all__ = ["Input", "Output", "main", "minimum_version", "out", "rule", "run", "task"]
