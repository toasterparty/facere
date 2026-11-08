"""facere.c: makefile_deps reads the files a compiler's depfile lists, and the module uses only Facere's public interface."""

import ast
from pathlib import Path

import pytest

import facere as fac
from facere import c


def _write_depfile(tmp_path: Path, text: str) -> str:
    depfile = tmp_path / "main.o.d"
    depfile.write_text(text, newline="")
    return str(depfile)


def test_fac_c_loads_on_first_use() -> None:
    assert fac.c.makefile_deps is c.makefile_deps


def test_gcc_depfile_lists_each_prerequisite_across_continuations(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "build/main.o: src/main.c src/a.h \\\n src/b.h\n")

    assert c.makefile_deps(depfile) == ["src/main.c", "src/a.h", "src/b.h"]


def test_crlf_continuations_read_alike(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "main.o: main.c \\\r\n a.h\r\n")

    assert c.makefile_deps(depfile) == ["main.c", "a.h"]


def test_phony_targets_add_nothing_and_a_file_listed_twice_appears_once(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "main.o: main.c a.h\n\na.h:\nother.o: a.h b.h\n")

    assert c.makefile_deps(depfile) == ["main.c", "a.h", "b.h"]


def test_comments_are_skipped_as_rustc_writes_them(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "app: src/main.rs\n\n# env-dep:KEY=value\n")

    assert c.makefile_deps(depfile) == ["src/main.rs"]


def test_escaped_blanks_hash_and_dollar_are_undone(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, r"main.o: my\ dir/a.h b\#c.h d$$e.h" + "\n")

    assert c.makefile_deps(depfile) == ["my dir/a.h", "b#c.h", "d$e.h"]


def test_backslashes_before_a_blank_halve_and_others_stay(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "main.o: C:\\src\\a.h end\\\\ b\\\\\\ c.h\n")

    assert c.makefile_deps(depfile) == ["C:\\src\\a.h", "end\\", "b\\ c.h"]


def test_windows_target_splits_at_the_colon_before_a_blank(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "C:/out/main.o: C:/src/main.c\n")

    assert c.makefile_deps(depfile) == ["C:/src/main.c"]


def test_line_naming_no_target_fails_rather_than_losing_a_file(tmp_path: Path) -> None:
    depfile = _write_depfile(tmp_path, "main.o: main.c\nnot a rule\n")

    with pytest.raises(ValueError, match="not a rule"):
        c.makefile_deps(depfile)


def test_extension_uses_only_the_public_interface() -> None:
    source = Path(c.__file__).read_text(encoding="utf-8")

    used = {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "fac"
    }

    assert used <= set(fac.__all__)
