"""C support, using only Facere's public interface."""

import re

import facere as fac

_TARGET_END = re.compile(r":(?=\s|$)")
_SPECIAL = re.compile(r"(\\*)([ \t])|\\#|\$\$")


def makefile_deps(path: str) -> list[str]:
    """Return the files the depfile at `path` lists, each once in order, for `fac.add_inputs`.

    The depfile is the Makefile fragment that gcc, clang, nvcc, and `rustc --emit=dep-info` write. Raises ValueError for a line that names no target.
    """
    text = fac.read_text(path).replace("\\\n", " ")
    files: dict[str, None] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        target_end = _TARGET_END.search(line)
        if target_end is None:
            raise ValueError(f"{path}: this line names no target: {line!r}")
        files.update(dict.fromkeys(_split_paths(line[target_end.end() :])))
    return list(files)


def _split_paths(text: str) -> list[str]:
    """Return the paths in `text`, separated by unescaped blanks, undoing the escapes compilers write: backslashes doubled before a blank, then one more where the blank is part of the path, `\\#` for `#`, and `$$` for `$`."""
    paths = []
    path = ""
    position = 0
    for match in _SPECIAL.finditer(text):
        path += text[position : match.start()]
        position = match.end()
        backslashes, blank = match.groups()
        if blank is None:
            path += match.group()[-1]
            continue
        path += "\\" * (len(backslashes) // 2)
        if len(backslashes) % 2:
            path += blank
        elif path:
            paths.append(path)
            path = ""
    path += text[position:]
    return [*paths, path] if path else paths
