import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple


class Result(NamedTuple):
    status: int
    out: str
    err: str


Fac = Callable[..., Result]


def run_fac(root: Path, *args: str, python_flags: tuple[str, ...] = ()) -> Result:
    """Run `python -m facere ARGS...` in a subprocess started in `root`."""
    completed = subprocess.run(
        [sys.executable, *python_flags, "-m", "facere", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return Result(completed.returncode, completed.stdout, completed.stderr)


def edit(path: Path, old: str, new: str) -> None:
    """Replace `old`, which must occur, with `new` in the file at `path`."""
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
