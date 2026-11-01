"""The command line, `fac [TARGET...]`, also run in-process through fac.main."""

import argparse
import contextlib
import os
import sys
import types
from collections.abc import Generator

from facere import _build, _collect
from facere._context import Context, activate, normalize
from facere._diagnostics import Diagnostic, FacereError, Note, format_path, print_error
from facere._version import VERSION


def main(args: list[str]) -> int:
    """Run the fac command line in-process with `args`, the arguments after the program name, and return its exit status."""
    parser = argparse.ArgumentParser(
        prog="fac",
        description="Build the targets the fac.py in the root defines.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help="a rule or task name, or a path a rule outputs relative to the root (default: the defaults fac.py declares)",
    )
    parser.add_argument(
        "-C",
        dest="directory",
        metavar="DIR",
        help="run as if started in DIR, which becomes the root",
    )
    parser.add_argument(
        "--out",
        default="build",
        metavar="DIR",
        help="output directory, relative to the root (default: build)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="hide the output of every successful command"
    )
    parser.add_argument("--version", action="version", version=VERSION)
    try:
        options = parser.parse_intermixed_args(args)
        if "" in (options.out, options.directory):
            parser.error("-C and --out take a directory, not an empty string")
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 1
    return _invoke(options.directory, options.out, options.quiet, options.targets)


def console_main() -> int:
    return main(sys.argv[1:])


def _invoke(directory: str | None, out: str, is_quiet: bool, targets: list[str]) -> int:
    start_dir = os.getcwd()
    root = os.path.abspath(os.path.join(start_dir, directory)) if directory else start_dir
    fac_py = os.path.join(root, "fac.py")
    if not os.path.isfile(fac_py):
        print_error(FacereError(_build_missing_root_error(root, start_dir)), start_dir)
        return 1
    context = Context(root=root, out_dir=normalize(out, root), fac_py=fac_py, is_quiet=is_quiet)
    pycache_prefix = os.path.abspath(os.path.join(root, context.state_dir, "pycache"))
    with _enter_root(root, pycache_prefix), activate(context):
        return _run(context, targets, start_dir)


@contextlib.contextmanager
def _enter_root(root: str, pycache_prefix: str) -> Generator[None]:
    """Run from `root`, importable and caching bytecode under `pycache_prefix`, then restore the interpreter and forget the modules imported from `root`."""
    start_dir = os.getcwd()
    saved_path = list(sys.path)
    saved_prefix = sys.pycache_prefix
    saved_modules = dict(sys.modules)
    try:
        os.chdir(root)
        sys.path.append(root)
        sys.pycache_prefix = pycache_prefix
        yield
    finally:
        os.chdir(start_dir)
        sys.path[:] = saved_path
        sys.pycache_prefix = saved_prefix
        _forget_modules(root, saved_modules)


def _run(context: Context, targets: list[str], start_dir: str) -> int:
    if sys.flags.optimize:
        print(
            "fac: warning: Python runs with assertions disabled, so no recipe's assert checks anything: drop -O and PYTHONOPTIMIZE",
            file=sys.stderr,
        )
    try:
        project = _collect.collect(context)
        summary = _build.build(
            context, project, _build.resolve_targets(project, context.root, targets)
        )
    except FacereError as error:
        print_error(error, start_dir)
        return 1
    except _build.RecipeFailure as failure:
        _build.report_failure(failure, start_dir)
        return 1
    except KeyboardInterrupt:
        print("fac: interrupted", file=sys.stderr)
        return 130
    print(f"fac: {summary.executed} executed, {summary.up_to_date} up to date", file=sys.stderr)
    return 0


def _build_missing_root_error(root: str, start_dir: str) -> Diagnostic:
    where = "the working directory" if root == start_dir else format_path(root, start_dir)
    message = f"no fac.py in {where}: run fac in the directory holding the project's fac.py, or name that directory with -C"
    ancestor = _find_ancestor_with_fac_py(root)
    if ancestor is None:
        return Diagnostic(None, message)
    relative = format_path(ancestor, start_dir)
    note = f"the nearest directory holding a fac.py is {relative}: run fac -C {relative}"
    return Diagnostic(None, message, (Note(None, note),))


def _find_ancestor_with_fac_py(directory: str) -> str | None:
    while True:
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent
        if os.path.isfile(os.path.join(directory, "fac.py")):
            return directory


def _forget_modules(root: str, saved_modules: dict[str, types.ModuleType]) -> None:
    prefix = os.path.join(root, "")
    for name, module in list(sys.modules.items()):
        if name in saved_modules:
            continue
        path = getattr(module, "__file__", None)
        if name == _collect.MODULE_NAME or (
            isinstance(path, str) and os.path.abspath(path).startswith(prefix)
        ):
            del sys.modules[name]
    if _collect.MODULE_NAME in saved_modules:
        sys.modules[_collect.MODULE_NAME] = saved_modules[_collect.MODULE_NAME]
