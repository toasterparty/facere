"""The undeclared-path check: a rule's recipe fails when it uses a file under the root, or a path a rule outputs, that its rule doesn't declare and its recipe hasn't reported. The same audit hook notes what collection reads and lists, for a cycle of a watch, and gives the terminal to a rule's recipe that calls `breakpoint()`."""

import os
import re
import sys
import threading
from typing import cast

from facere._context import (
    Context,
    Recipe,
    UndeclaredUse,
    calc_path_key,
    find_context,
    is_under_root,
    is_within,
    is_within_any,
    normalize,
)
from facere._observed import note_listed, note_read
from facere._output import ensure_held_for_debugger

_FLAG_SEPARATORS = re.compile("[=,]")
_WRITE_ACCESS = os.O_WRONLY | os.O_RDWR
# What threading.Thread.start raises, before Python 3.13 and from it, each with the thread's bound method first.
_THREAD_STARTS = ("_thread.start_new_thread", "_thread.start_joinable_thread")

_is_audit_hook_added = False


class UndeclaredPathError(Exception):
    pass


def validate_command_args(
    context: Context, recipe: Recipe, argv: list[str], cwd: str | None
) -> None:
    """Raise UndeclaredPathError for a path in `argv` that the rule executing `recipe` doesn't declare: a program holding a separator, against the root, or an argument or its parts split at `=` and `,`, against `cwd`."""
    if recipe.is_task:
        return
    program, *args = argv
    if "/" in program or os.sep in program:
        _validate_used(context, recipe, program, "ran")
    for arg in args:
        for part in {arg, *_FLAG_SEPARATORS.split(arg)} - {""}:
            _validate_used(context, recipe, os.path.join(cwd or "", part), "gave a command")


def validate_program(context: Context, recipe: Recipe, program: str) -> None:
    """Raise UndeclaredPathError when the resolved, absolute `program` is one the rule executing `recipe` doesn't declare."""
    if not recipe.is_task:
        _validate_used(context, recipe, program, "ran")


def ensure_audit_hook() -> None:
    """Add the hook that checks what recipes open, gives the terminal to a rule's debugger, and notes what collection opens and lists for a watch, once per process, since PEP 578 hooks can't be removed."""
    global _is_audit_hook_added
    if not _is_audit_hook_added:
        sys.addaudithook(_on_audit)
        _is_audit_hook_added = True


def note_misuse(context: Context, caller: str) -> None:
    """Fail the rule whose recipe started the calling thread, if one did, for calling `caller`, which only a recipe's own thread may, so the rule fails though its recipe never sees what the call raised."""
    for starter in context.find_starters():
        if starter.misuse is None:
            starter.misuse = f"a thread its recipe started called {caller}, which in a rule works only on the recipe's own thread"


def _on_audit(event: str, args: tuple[object, ...]) -> None:
    if event != "open":
        if event in _THREAD_STARTS:
            _on_thread_start(args)
        elif event == "os.scandir":
            _on_scandir(args)
        elif event == "builtins.breakpoint":
            _on_breakpoint()
        return
    context = find_context()
    if context is None:
        return
    if context.is_loading:
        _on_load_open(context, args)
        return
    # Only the thread a rule's recipe executes on has one, so rules executing at once are each checked against their own.
    recipe = context.find_rule_recipe()
    if recipe is None:
        return
    path, _, flags = args
    if not isinstance(path, str | bytes | os.PathLike) or not isinstance(flags, int):
        return
    absolute = _to_absolute(path)
    key = calc_path_key(normalize(absolute, context.root))
    access = flags & _WRITE_ACCESS
    if access != os.O_WRONLY and key not in recipe.shared_modules:
        _validate_used(context, recipe, absolute, "opened")
    if access != os.O_RDONLY:
        recipe.written.add(key)


def _on_load_open(context: Context, args: tuple[object, ...]) -> None:
    observed = context.observed
    if observed is None:
        return
    path, _, flags = args
    if not isinstance(path, str | bytes | os.PathLike) or not isinstance(flags, int):
        return
    if flags & _WRITE_ACCESS != os.O_WRONLY:
        note_read(observed, context, _to_absolute(path))


def _on_scandir(args: tuple[object, ...]) -> None:
    context = find_context()
    if context is None or not context.is_loading or context.observed is None:
        return
    (path,) = args
    if path is None:
        path = "."
    if isinstance(path, str | bytes | os.PathLike):
        note_listed(context.observed, context, _to_absolute(path))


def _to_absolute(path: object) -> str:
    return os.path.abspath(os.fsdecode(cast("str | bytes | os.PathLike[str]", path)))


def _on_breakpoint() -> None:
    context = find_context()
    # Python's own hook reads the variable on every call, and 0 makes breakpoint() do nothing.
    if context is None or os.environ.get("PYTHONBREAKPOINT") == "0":
        return
    recipe = context.find_rule_recipe()
    if recipe is not None:
        ensure_held_for_debugger(context, recipe)


def _on_thread_start(args: tuple[object, ...]) -> None:
    context = find_context()
    thread = getattr(args[0], "__self__", None) if args else None
    if context is not None and isinstance(thread, threading.Thread):
        context.note_started(thread)


def _validate_used(context: Context, recipe: Recipe, path: str, action: str) -> None:
    relative = normalize(path, context.root)
    key = calc_path_key(relative)
    is_exempt = (
        is_within_any(key, recipe.tracked)
        or is_within_any(key, recipe.order_only)
        or key in recipe.exempt
        or key in recipe.reported_keys
        or key in recipe.written
    )
    if is_exempt:
        return
    if is_within_any(key, recipe.output_keys) or _is_project_file(context, relative):
        reason = f"its recipe {action} {relative}, which no fac.Input parameter declares"
        recipe.undeclared = recipe.undeclared or UndeclaredUse(relative, reason)
        raise UndeclaredPathError(reason)


def _is_project_file(context: Context, relative: str) -> bool:
    """Say whether `relative` is a file under the root, outside the output directory and any hidden directory, where a virtual environment lives."""
    absolute = os.path.join(context.root, relative)
    if not is_under_root(absolute, context.root) or is_within(relative, context.out_dir):
        return False
    if any(part.startswith(".") for part in relative.split("/")[:-1]):
        return False
    return os.path.isfile(absolute)
