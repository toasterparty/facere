"""The c-hello example, which the C guide builds up to, compiled with zig through uvx."""

import re
import shutil
import sys
from pathlib import Path

import pytest

from ..helpers import EXAMPLES, REPO, closing_line, copy_example, edit, run_fac

GUIDE = REPO / "doc" / "user" / "9-building-c.md"
PROGRAM = "app.exe" if sys.platform == "win32" else "app"


def test_c_hello_is_the_project_the_c_guide_finishes_with() -> None:
    listings = re.findall(r"^```python\n(.*?)^```", GUIDE.read_text(encoding="utf-8"), re.M | re.S)

    assert listings[-1] == (EXAMPLES / "c-hello" / "fac.py").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("uvx") is None, reason="the example runs zig through uvx")
def test_c_hello_rebuilds_exactly_what_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GREETING", raising=False)
    root = copy_example("c-hello", tmp_path)

    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules."
    assert (
        closing_line(root, "app") == "Finished in <elapsed>. No work to do. 3 outputs up to date."
    )

    (root / "src" / "main.c").touch()
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 3 outputs up to date."

    with (root / "src" / "greeting.c").open("a") as source:
        source.write("// comment\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date."

    with (root / "src" / "greeting.h").open("a") as header:
        header.write("// comment\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 1 output up to date."

    edit(root / "fac.py", "import sys\n", "import sys  # the platform names the program\n")
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 3 outputs up to date."

    with (root / "build" / PROGRAM).open("ab") as program:
        program.write(b"\0")
    assert closing_line(root) == "Finished in <elapsed>. Executed 1 rule. 2 outputs up to date."

    assert closing_line(root, "build/src/main.o") == (
        "Finished in <elapsed>. No work to do. 1 output up to date."
    )

    monkeypatch.setenv("GREETING", "bonjour")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules."
    assert run_fac(root, "run").out == "bonjour\n"
    monkeypatch.delenv("GREETING")

    ran = run_fac(root, "clean", "run")
    assert ran.status == 0, ran.err
    assert ran.out == "hello, world\n"
    assert ran.err.splitlines()[-1] == "Finished in <elapsed>. Executed 2 tasks and 3 rules."
