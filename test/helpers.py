import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

REPO = Path(__file__).parents[1]
EXAMPLES = REPO / "doc" / "examples"


class Result(NamedTuple):
    status: int
    out: str
    err: str


Fac = Callable[..., Result]

_ELAPSED = re.compile(
    r"(Finished in|(?:Failed|Stopped|Interrupted) after) (?:\d+hr )?(?:\d+min )?(?:\d+\.\ds|\d+ms)"
)


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


def start_fac(root: Path, *args: str) -> subprocess.Popen[str]:
    """Start `python -m facere ARGS...` in `root` and return it, with its stderr a pipe."""
    return subprocess.Popen(
        [sys.executable, "-m", "facere", *args], cwd=root, stderr=subprocess.PIPE, text=True
    )


def wait_for(path: Path) -> str:
    """Wait until the file at `path` holds something, and return its text."""
    deadline = time.monotonic() + 30
    while not (path.exists() and path.read_text()):
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.01)
    return path.read_text()


def is_running(pid: int) -> bool:
    if sys.platform == "win32":
        # os.kill(pid, 0) on Windows terminates the process rather than probing it.
        import ctypes
        from ctypes import wintypes

        query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            assert kernel32.GetExitCodeProcess(wintypes.HANDLE(handle), ctypes.byref(exit_code))
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def run_in_new_console(driver: str, scratch: Path, *args: str | Path) -> dict[str, Any]:
    """Run the Python source `driver` in a console of its own on Windows, with `ARGS...` and then a report path as its arguments, and return the JSON object it wrote to the report.

    Its stdin is empty and its stdout and stderr are pipes, so a driver failing shows its traceback, and a child that needs the console opens `CONIN$` and `CONOUT$`.
    """
    assert sys.platform == "win32"
    script = scratch / "driver.py"
    script.write_text(driver)
    report = scratch / "report.json"
    completed = subprocess.run(
        [sys.executable, script, *args, report],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    assert completed.returncode == 0, f"the driver failed:\n{completed.stdout}{completed.stderr}"
    return json.loads(report.read_text())


def _read_change_time_ns(path: Path) -> int:
    if sys.platform == "win32":
        # os.stat's st_ctime_ns is the creation time on Windows, which no later write moves.
        from facere._filesystem import read_change_time_ns

        return read_change_time_ns(str(path))
    return path.stat().st_ctime_ns


def wait_for_later_change_time(path: Path) -> None:
    """Return once a file written now gets a later change time than `path`, as an edit made after an invocation does once the file system's clock ticks."""
    probe = path.with_name(".tick")
    probe.write_bytes(b"")
    deadline = time.monotonic() + 30
    while _read_change_time_ns(probe) <= _read_change_time_ns(path):
        assert time.monotonic() < deadline, f"no write got a later change time than {path}"
        probe.write_bytes(b"")
    probe.unlink()


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
