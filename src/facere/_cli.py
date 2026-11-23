"""The command line, `fac [TARGET...] [-- ARG...]`, also run in-process through fac.main."""

import argparse
import contextlib
import importlib
import os
import posixpath
import signal
import sys
import time
import types
from collections.abc import Generator

from facere import _build, _bytecode, _collect
from facere._command import Commands
from facere._context import (
    STATE_DIR_NAME,
    STATE_FILE_NAME,
    Context,
    Location,
    activate,
    normalize,
)
from facere._diagnostics import (
    Diagnostic,
    FacereError,
    Note,
    format_entering,
    format_leaving,
    format_line,
    format_path,
    print_error,
    print_warning,
)
from facere._lock import LockTimeoutError, OutputLock, describe_wait
from facere._observed import Observed, calc_watch_key
from facere._output import Output, capture_recipes
from facere._schedule import Signals, enable_interrupts, watch_signals
from facere._status import pin_status
from facere._summary import Outcome, Summary, format_summary
from facere._undeclared import ensure_audit_hook
from facere._version import VERSION

_HELP_EPILOG = """\
arguments after --:
  Facere parses nothing after --. Each ARG goes to every task among the
  targets that takes fac.Args, and at least one must when any ARG is given.

exit status:
  0    every target was built
  1    a recipe failed, or an output changed after its rule finished
  2    the build could not start: the command line, a fac.py, or a target is in error
  3    --lock-timeout ran out while another invocation held the output directory
  4    Facere itself raised, a bug, printed with its traceback
  130  the invocation was interrupted
  143  the invocation was asked to stop, as SIGTERM asks, and let the rules executing finish

Every invocation that parsed its arguments ends on a line starting with
Finished, Failed, Stopped, or Interrupted. With --watch, each build starts
with a line starting with "fac: change in", but for the first, and ends with
the line "fac: watching for changes".
"""
_AUTO = "auto"
_EDITED_OUTSIDE_RECIPES = (
    "code outside recipes changed, which executes no rule until fac.epoch rises"
)


def main(args: list[str]) -> int:
    """Run the fac command line in-process with `args`, the arguments after the program name, and return its exit status."""
    parser = argparse.ArgumentParser(
        prog="fac",
        usage="%(prog)s [-h] [-C DIR] [--out DIR] [-j N] [-k] [--lock-timeout SECONDS] [-q] [-v] [--watch] [--version] [TARGET ...] [-- ARG ...]",
        description="Build each TARGET of the project the fac.py in the root defines, in the order given.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help="a rule or task name, which covers every rule its function defines, or, when it contains a path separator, one path a rule outputs, relative to the root. Without a TARGET, every rule and task declared with default=True, or else every rule and no task. Consecutive targets that name no task are built together, and a task executes alone, once the targets before it are built",
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
        "-j",
        "--jobs",
        type=_parse_jobs,
        default=None,
        metavar="N",
        help="how many rules may execute at once, or auto for every CPU Facere may use (default: auto)",
    )
    parser.add_argument(
        "-k",
        "--keep-going",
        action="store_true",
        help="after a failure, still build everything that does not depend on what failed",
    )
    parser.add_argument(
        "--lock-timeout",
        type=_parse_seconds,
        default=None,
        metavar="SECONDS",
        help="fail with status 3 instead of waiting longer than SECONDS for another invocation on the same output directory, where 0 fails at once (default: wait as long as it takes)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="hide the output of every successful command not running live, as fac.Console.ON_FAILURE does",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print each command, as one string, before it runs",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="build the targets, then build them again whenever a file the last build read, or a directory it listed, changes, until interrupted. A change during a build stops it as SIGTERM does, and every task among the targets restarts on each change",
    )
    # A cycle of a watch, which records in the state what it observed, for the watch to poll.
    parser.add_argument("--watched", action="store_true", help=argparse.SUPPRESS)
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
    if options.watch:
        return _watch(options, args, task_args)
    if options.watched:
        enable_interrupts()
    return _invoke(options, task_args)


def console_main() -> int:
    return main(sys.argv[1:])


def _watch(options: argparse.Namespace, args: list[str], task_args: tuple[str, ...] | None) -> int:
    """Watch the targets, each cycle running fac on `args`, the arguments before any `--`, less --watch, then `--` and `task_args`."""
    root = _resolve_root(options.directory) if options.directory is not None else os.getcwd()
    state_dir = os.path.join(root, normalize(options.out, root), STATE_DIR_NAME)
    cycle_args = [arg for arg in args if arg != "--watch"]
    if task_args is not None:
        cycle_args.extend(["--", *task_args])
    state_path = os.path.join(state_dir, STATE_FILE_NAME)
    # Imported here, since it imports subprocess, which a build that runs no command never needs.
    from facere._watch import watch

    return watch(cycle_args, root, state_path, calc_watch_key(options.targets))


def _parse_jobs(text: str) -> int | None:
    if text == _AUTO:
        return None
    if not text.isdecimal() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"takes a count of 1 or more, or {_AUTO}, not {text!r}")
    return int(text)


def _parse_seconds(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        seconds = -1.0
    # Also rejects nan, which compares false.
    if not 0 <= seconds < float("inf"):
        raise argparse.ArgumentTypeError(f"takes a number of seconds, 0 or more, not {text!r}")
    return seconds


def _invoke(options: argparse.Namespace, task_args: tuple[str, ...] | None) -> int:
    """Run the invocation the parsed `options` ask for, end it on the closing line, and return its exit status."""
    start_dir = os.getcwd()
    start_s = time.perf_counter()
    summary = Summary()
    root = _resolve_root(options.directory) if options.directory is not None else start_dir
    if options.directory is not None:
        print(format_entering(root), file=sys.stderr)
    with watch_signals() as signals:
        outcome = _try_run(options, task_args, root, start_dir, summary, signals)
    if summary.edited:
        edits = [
            Diagnostic(Location(path, 1, 1), _EDITED_OUTSIDE_RECIPES) for path in summary.edited
        ]
        print_warning(_merge(edits, ", as in {} more file{}"), start_dir)
    if summary.unsettled:
        print_warning(_merge(summary.unsettled, ", as for {} more rule{}"), start_dir)
    if summary.ended:
        note = _merge(summary.ended, ", and {} more recipe{}")
        print(format_line(note, "note", start_dir), file=sys.stderr)
    if options.directory is not None:
        print(format_leaving(root), file=sys.stderr)
    print(format_summary(summary, time.perf_counter() - start_s, outcome), file=sys.stderr)
    if signals.is_hung_up and sys.platform != "win32":
        # Everything is cleaned up, so the signal now ends the process as it would have.
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGHUP)
    return outcome.value


def _merge(diagnostics: list[Diagnostic], more: str) -> Diagnostic:
    """Return the first of `diagnostics` counting the rest through `more`, so an invocation's own output stays within three lines."""
    first, *others = diagnostics
    if not others:
        return first
    counted = more.format(len(others), "" if len(others) == 1 else "s")
    return Diagnostic(first.location, first.message + counted)


def _try_run(
    options: argparse.Namespace,
    task_args: tuple[str, ...] | None,
    root: str,
    start_dir: str,
    summary: Summary,
    signals: Signals,
) -> Outcome:
    """Run the invocation, printing whatever kept it from finishing, and return how it ended."""
    try:
        _run(options, task_args, root, start_dir, summary, signals)
    except FacereError as error:
        print_error(error, start_dir)
        return Outcome.UNSTARTED
    except LockTimeoutError as error:
        print(f"fac: error: {error}", file=sys.stderr)
        return Outcome.LOCK_TIMEOUT
    except KeyboardInterrupt:
        return Outcome.INTERRUPTED
    except Exception:  # noqa: BLE001 - whatever Facere itself raises is reported as its bug
        import traceback

        traceback.print_exc()
        print("fac: error: Facere itself raised this, which is a bug in Facere", file=sys.stderr)
        return Outcome.CRASHED
    if summary.failed:
        return Outcome.FAILED
    return Outcome.STOPPED if signals.is_stop_requested else Outcome.FINISHED


def _run(
    options: argparse.Namespace,
    task_args: tuple[str, ...] | None,
    root: str,
    start_dir: str,
    summary: Summary,
    signals: Signals,
) -> None:
    fac_py = os.path.join(root, "fac.py")
    if not os.path.isfile(fac_py):
        raise FacereError(_build_missing_root_error(root, start_dir))
    out_dir = normalize(options.out, root)
    if out_dir == ".":
        message = "--out names the root, where outputs would mix with sources"
        raise FacereError(Diagnostic(None, message))
    if sys.flags.optimize:
        print(
            "fac: warning: Python runs with assertions disabled, so no recipe's assert checks anything",
            file=sys.stderr,
        )
    context = Context(
        root=root,
        out_dir=out_dir,
        fac_py=fac_py,
        is_quiet=options.quiet,
        is_verbose=options.verbose,
        has_terminal=_is_terminal(sys.stdin) and _is_terminal(sys.stderr),
        commands=Commands(),
        window_size=_try_fetch_window_size(),
        observed=Observed(options.targets) if options.watched else None,
    )
    lock = OutputLock(out_dir, os.path.join(root, context.state_dir))

    def take_lock() -> None:
        if not lock.is_held:
            lock.take(
                options.lock_timeout,
                lambda holder: print(
                    f"fac: note: {describe_wait(holder, out_dir)}", file=sys.stderr, flush=True
                ),
            )

    pycache_prefix = os.path.abspath(os.path.join(root, context.state_dir, "pycache"))
    with _enter_root(root, pycache_prefix) as saved_modules, activate(context):
        has_collected = False

        def collect() -> _collect.Project:
            nonlocal has_collected
            if has_collected:
                context.forget_collection()
                _forget_modules(root, saved_modules)
                importlib.invalidate_caches()
            has_collected = True
            _bytecode.ensure_checked(root)
            if context.observed is None:
                return _collect.collect(context)
            ensure_audit_hook()
            try:
                return _collect.collect(context)
            except FacereError:
                context.observed.is_extending = True
                raise

        try:
            take_lock()
            project = collect()
            with (
                pin_status(sys.stderr) as status_cb,
                capture_recipes(context) as (stdout, stderr),
            ):
                context.output = Output(stdout, stderr, status_cb)
                invocation = _build.Invocation(
                    context=context,
                    signals=signals,
                    summary=summary,
                    lock=lock,
                    start_dir=start_dir,
                    collect_cb=collect,
                    take_lock_cb=take_lock,
                    calc_jobs=lambda: options.jobs or _calc_default_jobs(),
                    keep_going=options.keep_going,
                    task_args=task_args,
                )
                _build.build(invocation, project, options.targets)
        finally:
            if context.observed is not None and lock.is_held:
                state_path = posixpath.join(context.state_dir, STATE_FILE_NAME)
                with contextlib.suppress(OSError):
                    context.observed.save(state_path)
            lock.give()


def _calc_default_jobs() -> int:
    # Imported here, since a build that executes no more than one rule never asks.
    from facere._jobs import calc_default_jobs

    return calc_default_jobs()


def _is_terminal(stream: object) -> bool:
    try:
        return bool(stream.isatty())  # ty: ignore[missing-attribute]
    except (AttributeError, ValueError):
        return False


def _try_fetch_window_size() -> tuple[int, int] | None:
    """Return the rows and columns of the terminal Facere's stderr is, where a rule's command may get one like it, or None."""
    if sys.platform == "win32" or not _is_terminal(sys.stderr):
        return None
    try:
        size = os.get_terminal_size(sys.stderr.fileno())
    except (OSError, ValueError):
        return None
    return size.lines, size.columns


def _resolve_root(directory: str) -> str:
    """Return `directory` as `os.getcwd()` names it once inside, resolved except on Windows, so a path a recipe makes absolute compares with the root lexically."""
    if sys.platform == "win32":
        return os.path.abspath(directory)
    return os.path.realpath(directory)


@contextlib.contextmanager
def _enter_root(root: str, pycache_prefix: str) -> Generator[dict[str, types.ModuleType]]:
    """Run from `root`, importable and caching bytecode under `pycache_prefix`, then restore the interpreter and forget the modules imported from `root`. Yields the modules imported before, which loading the project again keeps."""
    start_dir = os.getcwd()
    saved_path = list(sys.path)
    saved_prefix = sys.pycache_prefix
    saved_modules = dict(sys.modules)
    try:
        os.chdir(root)
        sys.path.append(root)
        # The import system caches directory listings, which a coarse mtime may leave stale across in-process invocations.
        importlib.invalidate_caches()
        sys.pycache_prefix = pycache_prefix
        yield saved_modules
    finally:
        os.chdir(start_dir)
        sys.path[:] = saved_path
        sys.pycache_prefix = saved_prefix
        _forget_modules(root, saved_modules)


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
        if name == _collect.MODULE_NAME or _collect.is_from_root(root, module):
            del sys.modules[name]
    if _collect.MODULE_NAME in saved_modules:
        sys.modules[_collect.MODULE_NAME] = saved_modules[_collect.MODULE_NAME]
