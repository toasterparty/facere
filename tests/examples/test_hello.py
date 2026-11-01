"""The hello example, built with zig from the ziglang package, which needs uvx and the network or a warm uv cache."""

import shutil
import sys
from pathlib import Path

import pytest

from tests.helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "examples" / "hello"
PROGRAM = "hello.exe" if sys.platform == "win32" else "hello"


@pytest.mark.skipif(shutil.which("uvx") is None, reason="the example runs zig through uvx")
def test_hello_rebuilds_exactly_what_changed(tmp_path: Path) -> None:
    root = tmp_path / "hello"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build"))

    first = run_fac(root)
    second = run_fac(root)
    edit(root / "fac.py", '"-O2", ', '"-O1", ')
    flags_changed = run_fac(root)
    edit(root / "fac.py", "import sys\n", "import sys  # the platform decides the program's name\n")
    comment_changed = run_fac(root)
    with (root / "build" / PROGRAM).open("ab") as program:
        program.write(b"\0")
    program_edited = run_fac(root)
    ran = run_fac(root, "run")

    assert first.status == 0, first.err
    assert first.err.splitlines()[-1] == "fac: 2 executed, 0 up to date"
    assert second.err.splitlines()[-1] == "fac: 0 executed, 2 up to date"
    assert flags_changed.err.splitlines()[-1] == "fac: 2 executed, 0 up to date"
    assert comment_changed.err.splitlines()[-1] == "fac: 0 executed, 2 up to date"
    assert program_edited.err.splitlines()[-1] == "fac: 1 executed, 1 up to date"
    assert ran.status == 0, ran.err
    assert ran.out == "hello, world\n"
