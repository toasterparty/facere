import importlib.util
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

REPO = Path(__file__).parents[1]
EXAMPLES = REPO / "doc" / "examples"


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


def closing_line(root: Path, *args: str) -> str:
    """Return the last line of stderr from `run_fac(root, *args)`, which must succeed."""
    result = run_fac(root, *args)
    assert result.status == 0, result.err
    return result.err.splitlines()[-1]


def copy_example(name: str, tmp_path: Path) -> Path:
    """Return a copy under `tmp_path` of the example `name`, less anything a run generated."""
    root = tmp_path / name
    generated = shutil.ignore_patterns("build", "__pycache__", "table.txt")
    shutil.copytree(EXAMPLES / name, root, ignore=generated)
    return root


def load_module(path: Path) -> ModuleType:
    """Return the module at `path`, which `--import-mode=importlib` leaves off `sys.path`."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def edit(path: Path, old: str, new: str) -> None:
    """Replace `old`, which must occur, with `new` in the file at `path`."""
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
