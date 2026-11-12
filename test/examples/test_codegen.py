"""The codegen example, compiled with zig through uvx, generating with gperf."""

import shutil
from pathlib import Path

import pytest

from ..helpers import closing_line, copy_example, edit, run_fac

pytestmark = pytest.mark.skipif(
    shutil.which("uvx") is None or shutil.which("gperf") is None,
    reason="the example runs zig through uvx, and gperf",
)


def _prepare(tmp_path: Path) -> Path:
    root = copy_example("codegen", tmp_path)
    assert closing_line(root) == "Finished in <elapsed>. Executed 9 rules."
    return root


def test_generated_code_rebuilds_exactly_what_read_it(tmp_path: Path) -> None:
    root = _prepare(tmp_path)
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 11 outputs up to date."
    assert run_fac(root, "run").out == "greeting: token 3, valid 1, session 1\n"

    with (root / "messages" / "login.toml").open("a") as spec:
        spec.write('session = "string"\n')
    assert closing_line(root) == "Finished in <elapsed>. Executed 4 rules. 6 outputs up to date."

    generator = root / "tools" / "messages.py"
    edit(generator, "import tomllib\n", "import tomllib  # reads specs\n")
    assert closing_line(root) == "Finished in <elapsed>. No work to do. 11 outputs up to date."

    edit(generator, "members", "fields_text")
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 7 outputs up to date."

    edit(generator, "message != 0", "message != (void *)0")
    assert closing_line(root) == "Finished in <elapsed>. Executed 5 rules. 4 outputs up to date."

    (root / "messages" / "logout.toml").write_text('[fields]\nuser = "string"\n')
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 10 outputs up to date."

    with (root / "src" / "keywords.gperf").open("a") as table:
        table.write("quit, 4\n")
    assert closing_line(root) == "Finished in <elapsed>. Executed 3 rules. 11 outputs up to date."

    (root / "login.h").write_text("")
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 12 outputs up to date."


def test_compile_reading_a_generated_header_needs_it_ordered(tmp_path: Path) -> None:
    root = _prepare(tmp_path)
    edit(root / "fac.py", ", headers: list[fac.OrderOnly] = HEADERS", "")

    result = run_fac(root)

    assert result.status == 1
    assert "build/gen/messages/greeting.h" in result.err
    assert "rule 'message' (build/gen/messages/greeting.h) outputs" in result.err


def test_generator_run_as_a_command_must_be_declared(tmp_path: Path) -> None:
    root = _prepare(tmp_path)
    edit(
        root / "fac.py",
        "messages.generate(spec, header, source)",
        'fac.run(sys.executable, "tools/messages.py", spec, header, source)',
    )

    result = run_fac(root)

    assert result.status == 1
    assert "its recipe gave a command tools/messages.py" in result.err


def test_missing_program_fails_only_a_rule_that_must_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _prepare(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert closing_line(root) == "Finished in <elapsed>. No work to do. 11 outputs up to date."

    with (root / "src" / "keywords.gperf").open("a") as table:
        table.write("quit, 4\n")
    result = run_fac(root)

    assert result.status == 1
    assert "'gperf'" in result.err
