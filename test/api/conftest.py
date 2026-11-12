from pathlib import Path

import pytest

import facere

from ..helpers import Fac, Result, mask_elapsed, pass_clock_tick


@pytest.fixture
def fac(root: Path, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Fac:
    """Return a function running `fac ARGS...` in-process from `cwd`, the root by default, capturing its streams."""

    def run(*args: str, cwd: Path = root) -> Result:
        monkeypatch.chdir(cwd)
        capfd.readouterr()
        pass_clock_tick(root.parent)
        status = facere.main(list(args))
        captured = capfd.readouterr()
        # Commands print their output unaltered, so on Windows a command's lines end in CRLF.
        return Result(
            status,
            captured.out.replace("\r\n", "\n"),
            mask_elapsed(captured.err.replace("\r\n", "\n")),
        )

    return run
