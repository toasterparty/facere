"""The command line, `fac [TARGET...] [-- ARG...]`, also run in-process through fac.main."""

import argparse
import contextlib
import os
import sys
import time
import types
from collections.abc import Generator

from facere import _build, _collect
from facere._context import Context, activate, is_under_root, normalize
from facere._diagnostics import Diagnostic, FacereError, Note, format_path, print_error
from facere._status import pin_status
from facere._summary import Summary, format_summary
from facere._version import VERSION

_HELP_EPILOG = """\
arguments after --:
  Facere parses nothing after --. Each ARG goes to every task among the
  targets that takes fac.Args, and at least one must when any ARG is given.

exit status:
  0    every target was built
  1    a recipe failed
  2    the build could not start: the command line, a fac.py, or a target is in error
  130  the invocation was interrupted
"""


def main(args: list[str]) -> int:
    """Run the fac command line in-process with `args`, the arguments after the program name, and return its exit status."""
    parser = argparse.ArgumentParser(
        prog="fac",
        usage="%(prog)s [-h] [-C DIR] [--out DIR] [-q] [-v] [--version] [TARGET ...] [-- ARG ...]",
        description="Build each TARGET of the project the fac.py in the root defines, in the order given.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help="a rule or task name, which covers every rule its function defines, or, when it contains a path separator, one path a rule outputs, relative to the root. Without a TARGET, every rule and task declared with default=True, or else every rule and no task",
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
        help="output directory, relative to the root and other than it (default: build)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="hide the output of every successful command"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print each command, as one string, before it runs",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    task_args = None
    if "--" in args:
        split = args.index("--")
        args, task_args = args[:split], tuple(args[split + 1 :])
    try:
        options = parser.parse_intermixed_args(args)
        if "" in (options.out, options.directory):
            parser.error("-C and --out take a directory, not an empty string")
        if task_args is not None and not options.targets:
            parser.error("-- passes arguments to the tasks among the targets, which name none")
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 1
    return _invoke(
        options.directory, options.out, options.quiet, options.verbose, options.targets, task_args
    )


def console_main() -> int:
    return main(sys.argv[1:])


def _invoke(
    directory: str | None,
    out: str,
    is_quiet: bool,
    is_verbose: bool,
    targets: list[str],
    task_args: tuple[str, ...] | None,
) -> int:
    start_dir = os.getcwd()
    root = os.path.abspath(directory) if directory is not None else start_dir
    fac_py = os.path.join(root, "fac.py")
    if not os.path.isfile(fac_py):
        print_error(FacereError(_build_missing_root_error(root, start_dir)), start_dir)
        return 2
    out_dir = normalize(out, root)
    if out_dir == ".":
        message = "--out names the root, where outputs would mix with sources"
        print_error(FacereError(Diagnostic(None, message)), start_dir)
        return 2
    context = Context(
        root=root, out_dir=out_dir, fac_py=fac_py, is_quiet=is_quiet, is_verbose=is_verbose
    )
    pycache_prefix = os.path.abspath(os.path.join(root, context.state_dir, "pycache"))
    with _enter_root(root, pycache_prefix), activate(context):
        return _run(context, targets, task_args, start_dir)


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


def _run(
    context: Context, targets: list[str], task_args: tuple[str, ...] | None, start_dir: str
) -> int:
    if sys.flags.optimize:
        print(
            "fac: warning: Python runs with assertions disabled, so no recipe's assert checks anything",
            file=sys.stderr,
        )
    start_s = time.perf_counter()
    summary = Summary()
    try:
        project = _collect.collect(context)
        resolved = _build.resolve_targets(project, context.root, targets)
        _build.validate_task_args(resolved, task_args)
        with pin_status(sys.stderr) as progress_cb:
            _build.build(context, project, resolved, summary, progress_cb, task_args)
    except FacereError as error:
        print_error(error, start_dir)
        return 2
    except _build.RecipeFailure as failure:
        _build.report_failure(failure, start_dir)
        return 1
    except KeyboardInterrupt:
        _print_summary(summary, start_s, is_interrupted=True)
        return 130
    _print_summary(summary, start_s, is_interrupted=False)
    return 0


def _print_summary(summary: Summary, start_s: float, *, is_interrupted: bool) -> None:
    elapsed_s = time.perf_counter() - start_s
    print(format_summary(summary, elapsed_s, is_interrupted=is_interrupted), file=sys.stderr)


def _build_missing_root_error(root: str, start_dir: str) -> Diagnostic:
    where = "the working directory" if root == start_dir else format_path(root, start_dir)
    message = f"no fac.py in {where}"
    ancestor = _find_ancestor_with_fac_py(root)
    if ancestor is None:
        return Diagnostic(None, message)
    relative = format_path(ancestor, start_dir)
    note = f"the nearest directory holding a fac.py is {relative}"
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
    for name, module in list(sys.modules.items()):
        if name in saved_modules:
            continue
        path = getattr(module, "__file__", None)
        if name == _collect.MODULE_NAME or (isinstance(path, str) and is_under_root(path, root)):
            del sys.modules[name]
    if _collect.MODULE_NAME in saved_modules:
        sys.modules[_collect.MODULE_NAME] = saved_modules[_collect.MODULE_NAME]
