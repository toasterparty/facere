import re
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

_ELAPSED = re.compile(r"(Finished in|Interrupted after) (?:\d+hr )?(?:\d+min )?(?:\d+\.\ds|\d+ms)")


def mask_elapsed(text: str) -> str:
    """Replace the elapsed time in fac's closing line, with `<elapsed>`, so a test can assert the rest as a literal."""
    return _ELAPSED.sub(r"\1 <elapsed>", text)


def run_fac(
    root: Path, *args: str, python_flags: tuple[str, ...] = (), stdin_text: str | None = None
) -> Result:
    """Run `python -m facere ARGS...` in a subprocess started in `root`, feeding it `stdin_text`."""
    completed = subprocess.run(
        [sys.executable, *python_flags, "-m", "facere", *args],
        cwd=root,
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return Result(completed.returncode, completed.stdout, mask_elapsed(completed.stderr))


def edit(path: Path, old: str, new: str) -> None:
    """Replace `old`, which must occur, with `new` in the file at `path`."""
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
