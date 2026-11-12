import re
import shutil
import subprocess

import pytest

from ..helpers import EXAMPLES


@pytest.fixture(scope="session", autouse=True)
def _installed_zig() -> None:
    """Install the compiler the C examples pin, before any of them builds.

    A compile that installs zig while it executes reads the headers it reports as changed during its recipe, so the next build executes it again, where each test expects that build to do nothing.
    """
    if shutil.which("uvx") is None:
        return
    fac_py = (EXAMPLES / "c-hello" / "fac.py").read_text(encoding="utf-8")
    pinned = re.search(r'^ZIG_VERSION = "(.+)"$', fac_py, re.MULTILINE)
    assert pinned is not None
    subprocess.run(
        ["uvx", "--from", f"ziglang=={pinned[1]}", "python-zig", "version"],
        check=True,
        capture_output=True,
    )
