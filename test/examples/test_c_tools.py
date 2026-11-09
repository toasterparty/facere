"""The c-tools example, compiled with zig through uvx, each other tool needed only by its task."""

import shutil
import sys
from pathlib import Path

import pytest

from ..helpers import closing_line, copy_example, edit, run_fac

pytestmark = pytest.mark.skipif(
    shutil.which("uvx") is None, reason="the example runs zig through uvx"
)

EXECUTED_BUILD = "Finished in <elapsed>. Executed 3 rules."


def _needs(tool: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(shutil.which(tool) is None, reason=f"the task runs {tool}")


def test_version_bump_rebuilds_only_what_reads_the_header(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)
    assert closing_line(root) == EXECUTED_BUILD
    assert (
        closing_line(root, "app") == "Finished in <elapsed>. No work to do. 3 outputs up to date."
    )

    bumped = run_fac(root, "bump", "app", "--", "minor")

    assert bumped.status == 0, bumped.err
    assert bumped.err.splitlines()[-1] == (
        "Finished in <elapsed>. Executed 1 task and 2 rules. 1 output up to date."
    )
    assert run_fac(root, "run").out == "app 1.3.0 over https\n"

    assert run_fac(root, "clean").status == 0
    assert closing_line(root) == EXECUTED_BUILD


def test_a_value_every_rule_receives_rebuilds_them_all(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)
    closing_line(root)

    edit(root / "fac.py", "-DENABLE_HTTPS=1", "-DENABLE_HTTPS=0")

    assert closing_line(root) == EXECUTED_BUILD
    assert run_fac(root, "run").out == "app 1.2.3 over http\n"


def test_flash_takes_its_port_after_the_separator_and_targets_run_in_order(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)

    short = run_fac(root, "flash", "--", "-p", "build/short")
    long = run_fac(root, "flash", "--", "--port", "build/long")
    flashed = run_fac(root, "flash", "monitor")

    assert short.out == "flashed build/short\n"
    assert long.out == "flashed build/long\n"
    assert flashed.status == 0, flashed.err
    assert flashed.out.splitlines()[-1] == "app 1.2.3 over https"


def test_verbose_prints_commands(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)

    assert " -c src/main.c -o build/src/main.o" in run_fac(root, "-v").err


def test_quiet_hides_a_warning_a_plain_build_shows(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)
    edit(root / "src" / "main.c", "int main(void) {", "int main(void) {\n    int unused;")

    plain = run_fac(root)
    quiet = run_fac(root, "--out", "other", "-q")

    assert "unused" in plain.err
    assert "unused" not in quiet.err


def test_out_moves_the_outputs_and_the_state_leaving_build_as_it_was(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)

    assert closing_line(root, "--out", "other") == EXECUTED_BUILD

    assert (root / "other" / "src" / "main.o").is_file()
    assert not (root / "build").exists()
    assert closing_line(root) == EXECUTED_BUILD


def test_a_project_needing_a_newer_facere_fails_before_any_recipe(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)
    edit(root / "fac.py", 'fac.minimum_version("0.3")', 'fac.minimum_version("99.0")')

    result = run_fac(root)

    assert result.status == 2
    assert "uv tool upgrade facere" in result.err
    assert not (root / "build" / "src").exists()


@_needs("clang-format")
def test_format_rewrites_the_sources_so_the_next_build_compiles_them(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)
    edit(
        root / "src" / "net.c", "const char *net_scheme(void) {", "const char *net_scheme(void)\n{"
    )
    assert closing_line(root) == EXECUTED_BUILD

    result = run_fac(root, "format")

    assert result.status == 0, result.err
    assert "const char *net_scheme(void) {" in (root / "src" / "net.c").read_text()
    assert closing_line(root) == "Finished in <elapsed>. Executed 2 rules. 1 output up to date."


@_needs("clang-check")
def test_check_passes_a_clean_tree(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)

    result = run_fac(root, "check")

    assert result.status == 0, result.err
    assert not (root / "build" / "app").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="binutils reads the ELF the build writes here")
@_needs("size")
@_needs("objdump")
def test_size_and_disassemble_read_the_program(tmp_path: Path) -> None:
    root = copy_example("c-tools", tmp_path)

    size = run_fac(root, "size")
    default = run_fac(root, "disassemble")
    named = run_fac(root, "disassemble", "--", "net_scheme")

    assert size.out.split()[:3] == ["text", "data", "bss"]
    assert "<main>:" in default.out
    assert "<net_scheme>:" in named.out


@_needs("valgrind")
def test_valgrind_runs_the_program(tmp_path: Path) -> None:
    result = run_fac(copy_example("c-tools", tmp_path), "valgrind")

    assert result.status == 0, result.err


def test_a_task_needing_a_missing_tool_fails_only_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_example("c-tools", tmp_path)
    closing_line(root)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert closing_line(root) == "Finished in <elapsed>. No work to do. 3 outputs up to date."
    result = run_fac(root, "size")

    assert result.status == 1
    assert "'size'" in result.err
