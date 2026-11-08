"""The undeclared-path check: a rule's recipe fails when it uses a file under the root, or a path a rule outputs, that its rule doesn't declare and its recipe hasn't reported."""

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

_FLAG_SEPARATORS = re.compile("[=,]")
_WRITE_ACCESS = os.O_WRONLY | os.O_RDWR

_is_audit_hook_added = False


class UndeclaredPathError(Exception):
    pass


def validate_command_args(context: Context, argv: list[str], cwd: str | None) -> None:
    """Raise UndeclaredPathError for a path in `argv` the running rule doesn't declare: a program holding a separator, against the root, or an argument or its parts split at `=` and `,`, against `cwd`."""
    recipe = context.running
    assert recipe is not None
    if recipe.is_task:
        return
    program, *args = argv
    if "/" in program or os.sep in program:
        _validate_used(context, recipe, program, "ran")
    for arg in args:
        for part in {arg, *_FLAG_SEPARATORS.split(arg)} - {""}:
            _validate_used(context, recipe, os.path.join(cwd or "", part), "gave a command")


def validate_program(context: Context, program: str) -> None:
    """Raise UndeclaredPathError when the resolved, absolute `program` is one the running rule doesn't declare."""
    recipe = context.running
    assert recipe is not None
    if not recipe.is_task:
        _validate_used(context, recipe, program, "ran")


def ensure_audit_hook() -> None:
    """Add the hook that checks what recipes open, once per process, since PEP 578 hooks can't be removed."""
    global _is_audit_hook_added
    if not _is_audit_hook_added:
        sys.addaudithook(_on_audit)
        _is_audit_hook_added = True


def _on_audit(event: str, args: tuple[object, ...]) -> None:
    if event != "open":
        return
    context = find_context()
    if context is None:
        return
    recipe = context.running
    if recipe is None or recipe.is_task or recipe.thread_id != threading.get_ident():
        return
    path, _, flags = args
    if not isinstance(path, str | bytes | os.PathLike) or not isinstance(flags, int):
        return
    absolute = os.path.abspath(os.fsdecode(cast("str | bytes | os.PathLike[str]", path)))
    key = calc_path_key(normalize(absolute, context.root))
    access = flags & _WRITE_ACCESS
    if access != os.O_WRONLY and key not in recipe.shared_modules:
        _validate_used(context, recipe, absolute, "opened")
    if access != os.O_RDONLY:
        recipe.written.add(key)


def _validate_used(context: Context, recipe: Recipe, path: str, action: str) -> None:
    relative = normalize(path, context.root)
    key = calc_path_key(relative)
    is_exempt = (
        is_within_any(key, recipe.tracked)
        or is_within_any(key, recipe.order_only)
        or key in recipe.exempt
        or key in recipe.reported
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
