"""The c-configurations example, compiled with zig through uvx."""

import shutil
from pathlib import Path

import pytest

from ..helpers import closing_line, copy_example, edit, run_fac


@pytest.mark.skipif(shutil.which("uvx") is None, reason="the example runs zig through uvx")
def test_a_configuration_rebuilds_apart_from_the_others(tmp_path: Path) -> None:
    root = copy_example("c-configurations", tmp_path)

    assert closing_line(root, "build/debug/src/main.o") == "Finished in <elapsed>. Executed 1 rule."
    assert closing_line(root) == "Finished in <elapsed>. Executed 5 rules. 1 output up to date."
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 6 outputs up to date."

    edit(root / "fac.py", 'BUILD_NAME="release"', 'BUILD_NAME="shipping"')
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 3 outputs up to date."

    ran = run_fac(root, "run_release")
    assert ran.out == "hello, world\nbuilt as shipping\n"
    assert run_fac(root, "run_debug").out == "hello, world\nbuilt as debug\n"
