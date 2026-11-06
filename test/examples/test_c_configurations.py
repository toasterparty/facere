"""The c-configurations example, compiled with zig through uvx."""

import shutil
from pathlib import Path

import pytest

from ..helpers import edit, run_fac

EXAMPLE = Path(__file__).parents[2] / "doc" / "examples" / "c-configurations"


@pytest.mark.skipif(shutil.which("uvx") is None, reason="the example runs zig through uvx")
def test_a_configuration_rebuilds_apart_from_the_others(tmp_path: Path) -> None:
    root = tmp_path / "c-configurations"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build"))

    def closing_line(*args: str) -> str:
        result = run_fac(root, *args)
        assert result.status == 0, result.err
        return result.err.splitlines()[-1]

    assert closing_line("build/debug/src/main.o") == "Finished in <elapsed>. Executed 1 rule."
    assert closing_line() == "Finished in <elapsed>. Executed 5 rules. 1 output up to date."
    assert closing_line() == "Finished in <elapsed>. No work to do. 6 outputs up to date."

    edit(root / "fac.py", 'BUILD_NAME="release"', 'BUILD_NAME="shipping"')
    assert closing_line() == "Finished in <elapsed>. Executed 3 rules. 3 outputs up to date."

    ran = run_fac(root, "run_release")
    assert ran.out == "hello, world\nbuilt as shipping\n"
    assert run_fac(root, "run_debug").out == "hello, world\nbuilt as debug\n"
