"""fac.run and fac.capture, which spawn one command from a recipe, and the commands an invocation is running, which an interrupt kills.

`subprocess` and `shutil` are imported only once a command runs, since together they cost an invocation that runs none 3 ms.
"""

from __future__ import annotations

import contextlib
import errno
import os
import shlex
import signal
import sys
import threading
from collections.abc import Generator, Mapping
from typing import IO, TYPE_CHECKING

from facere._context import Console, Context, Recipe, get_context
from facere._diagnostics import format_entering, format_leaving
from facere._output import Chunk, write_data
from facere._undeclared import note_misuse, validate_command_args, validate_program

if TYPE_CHECKING:
    import subprocess

_Stream = int | IO[bytes] | None
_Args = tuple[str | list[str] | tuple[str, ...], ...]
_READ_BYTES = 65536


class Commands:
    """The commands an invocation is running, so the main thread can end what the recipes' threads started."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Each command with whether it runs in a session of its own and whether a task runs it.
        self._running: dict[subprocess.Popen[bytes], tuple[bool, bool]] = {}
        self._is_killed = False
        self._are_tasks_stopped = False

    def try_add(self, process: subprocess.Popen[bytes], in_session: bool, is_task: bool) -> bool:
        """Count `process` as running, or return False where a kill or a stop already ended commands like it, so its spawner ends it."""
        with self._lock:
            if self.is_ended(is_task):
                return False
            self._running[process] = (in_session, is_task)
            return True

    def remove(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._running.pop(process, None)

    def is_ended(self, is_task: bool) -> bool:
        """Say whether a kill, or for a task's command a stop, ended the commands running then and refuses new ones."""
        return self._is_killed or (is_task and self._are_tasks_stopped)

    def kill(self) -> None:
        """Kill every running command, a rule's with its whole session, and refuse every later one."""
        with self._lock:
            self._is_killed = True
            running = list(self._running.items())
        for process, (in_session, _) in running:
            _send_kill(process, in_session)

    def stop_tasks(self) -> None:
        """Ask every command a task is running to end, as SIGTERM asks, and refuse a task's later ones.

        On Windows the console already sent each one the CTRL_BREAK_EVENT that asked Facere to stop.
        """
        with self._lock:
            self._are_tasks_stopped = True
            running = [
                (process, in_session)
                for process, (in_session, is_task) in self._running.items()
                if is_task
            ]
        if sys.platform == "win32":
            return
        for process, in_session in running:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                if in_session:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()


def run(
    *args: str | list[str] | tuple[str, ...],
    cwd: str | None = None,
    env: Mapping[str, str | None] | None = None,
    stdin: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    timeout: float | None = None,
    console: Console | None = None,
) -> None:
    """Run one command without a shell, raising subprocess.CalledProcessError on a non-zero exit.

    Each of `args` is one string, or a list or tuple of strings that contributes each of its items in order, so `fac.run(CC, CFLAGS, "-c", source)` needs no `*`. The first string is the program, the rest its arguments. The program resolves through `PATH`, or against the root when it contains a separator, and raises FileNotFoundError when it doesn't resolve. The command inherits Facere's environment, with what `fac.env` set over it, then `env` over both, where `None` unsets a variable. `cwd` is relative to the root. `stdin`, `stdout`, and `stderr` name files, relative to the root, to feed the command and fill, and a file both `stdout` and `stderr` name receives both streams.

    `console` takes the fac.Console member that says how the command meets the terminal, else the default fac.Console names. `timeout` kills the command after that many seconds and raises subprocess.TimeoutExpired. Call it on the recipe's own thread, or in a task from any thread.
    """
    context, recipe = _get_recipe("fac.run")
    mode = _resolve_console(context, recipe, console)
    _run(
        "fac.run",
        context,
        recipe,
        args,
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        timeout=timeout,
        is_live=mode is Console.LIVE,
        is_shown=mode is Console.AFTER,
    )


def capture(
    *args: str | list[str] | tuple[str, ...],
    cwd: str | None = None,
    env: Mapping[str, str | None] | None = None,
    stdin: str | None = None,
    stderr: str | None = None,
    timeout: float | None = None,
) -> str:
    """Run one command as `fac.run` does in a rule, and return its stdout decoded as UTF-8, printing nothing when it succeeds.

    It takes the arguments of `fac.run` but `stdout` and `console`, and behaves alike in a rule and a task: the command reads an empty stdin unless `stdin` names a file, and has no terminal.
    """
    context, recipe = _get_recipe("fac.capture")
    out = _run(
        "fac.capture",
        context,
        recipe,
        args,
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=None,
        stderr=stderr,
        timeout=timeout,
        is_live=False,
        is_shown=False,
    )
    return out.decode("utf-8", "surrogateescape")


def _get_recipe(caller: str) -> tuple[Context, Recipe]:
    context = get_context(caller)
    recipe = context.find_recipe()
    if recipe is None:
        note_misuse(context, caller)
        raise RuntimeError(
            f"{caller} runs a command only from the recipe of a rule or task, and in a rule only on the recipe's own thread"
        )
    return context, recipe


def _resolve_console(context: Context, recipe: Recipe, console: Console | None) -> Console:
    """Return the mode a command runs in: `console`, else its recipe's default, captured only on failure where `fac -q` asks."""
    if console is not None and not isinstance(console, Console):
        raise TypeError(f"fac.run takes a fac.Console member as console=, not {console!r}")
    if console is None:
        console = Console.LIVE if recipe.is_task else context.console
    if console is not Console.LIVE:
        return Console.ON_FAILURE if context.is_quiet else console
    if not recipe.is_task and not context.has_terminal:
        raise RuntimeError(
            "fac.run runs a rule's command with console=fac.Console.LIVE only where Facere's standard input and standard error are a terminal"
        )
    return console


def _run(
    caller: str,
    context: Context,
    recipe: Recipe,
    args: _Args,
    *,
    cwd: str | None,
    env: Mapping[str, str | None] | None,
    stdin: str | None,
    stdout: str | None,
    stderr: str | None,
    timeout: float | None,
    is_live: bool,
    is_shown: bool,
) -> bytes:
    """Run the command for `caller` and return what it wrote to a captured stdout.

    A live command shares Facere's streams, and in a rule holds the terminal while it runs. Any other is captured, and where `is_shown`, its output joins a rule's recipe's, or goes straight to Facere's streams in a task.
    """
    import subprocess

    argv = _flatten(caller, args)
    validate_command_args(context, recipe, argv, cwd)
    if context.is_verbose:
        print(shlex.join(argv), file=sys.stderr, flush=True)
    command_env = _build_env({**context.env, **(env or {})})
    program = _resolve_program(caller, argv[0], context.root, command_env)
    validate_program(context, recipe, program)
    captured = None if is_live else subprocess.PIPE
    with contextlib.ExitStack() as files:
        stdin_stream: _Stream = None if is_live else subprocess.DEVNULL
        stdout_stream: _Stream = captured
        stderr_stream: _Stream = captured
        if stdin is not None:
            stdin_stream = files.enter_context(open(stdin, "rb"))
        if stdout is not None:
            stdout_stream = files.enter_context(open(stdout, "wb"))
        if stderr is not None:
            stderr_stream = (
                subprocess.STDOUT
                if stdout is not None and _is_same_path(stderr, stdout)
                else files.enter_context(open(stderr, "wb"))
            )
        try:
            with _share_streams(context, recipe, cwd) if is_live else contextlib.nullcontext():
                returncode, out, err = _spawn(
                    context,
                    [program, *argv[1:]],
                    cwd=cwd,
                    env=command_env,
                    stdin=stdin_stream,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    timeout=timeout,
                    is_live=is_live,
                    is_task=recipe.is_task,
                )
        except subprocess.TimeoutExpired as error:
            # Without pipes, communicate() reports the time remaining, not the limit set.
            assert timeout is not None
            limit = subprocess.TimeoutExpired(argv, timeout, error.output, error.stderr)
            raise _locate(limit, cwd, is_live) from None
    if returncode != 0:
        failure = subprocess.CalledProcessError(
            returncode,
            argv,
            output=None if is_live else out.decode("utf-8", "surrogateescape"),
            stderr=None if is_live else err.decode("utf-8", "surrogateescape"),
        )
        raise _locate(failure, cwd, is_live)
    if is_shown and (err or out):
        _show(recipe, [(True, err), (False, out)], cwd)
    return out


def _locate(
    error: subprocess.SubprocessError, cwd: str | None, is_live: bool
) -> subprocess.SubprocessError:
    """Return `error` naming the directory its command ran in, for the lines Facere prints around the command's captured output."""
    if cwd is not None and not is_live:
        error.cwd = cwd  # ty: ignore[missing-attribute]
    return error


def _show(recipe: Recipe, chunks: list[Chunk], cwd: str | None) -> None:
    entering, leaving = _frame(cwd)
    chunks = [*entering, *chunks, *leaving]
    if recipe.is_task:
        _write_now(chunks)
    else:
        recipe.output.extend(chunks)


@contextlib.contextmanager
def _share_streams(context: Context, recipe: Recipe, cwd: str | None) -> Generator[None]:
    """Frame the block with the lines naming `cwd`, and in a rule hold the terminal for it, first writing what the recipe wrote so far, so its output keeps its order."""
    entering, leaving = _frame(cwd)
    if recipe.is_task:
        _write_now(entering)
        try:
            yield
        finally:
            _write_now(leaving)
        return
    assert context.output is not None
    before = [*recipe.output, *entering]
    recipe.output.clear()
    with context.output.hold_terminal(before, leaving):
        yield


def _frame(cwd: str | None) -> tuple[list[Chunk], list[Chunk]]:
    """Return the lines Facere prints before and after the output of a command that ran in `cwd`."""
    if cwd is None:
        return [], []
    return [(True, f"{format_entering(cwd)}\n")], [(True, f"{format_leaving(cwd)}\n")]


def _write_now(chunks: list[Chunk]) -> None:
    for is_stderr, data in chunks:
        write_data(sys.stderr if is_stderr else sys.stdout, data)


def _is_same_path(path: str, other: str) -> bool:
    return os.path.normcase(os.path.normpath(path)) == os.path.normcase(os.path.normpath(other))


def _flatten(caller: str, args: _Args) -> list[str]:
    argv = [item for arg in args for item in (arg if isinstance(arg, list | tuple) else [arg])]
    if not argv or not all(isinstance(item, str) for item in argv):
        raise TypeError(
            f"{caller} takes the program and its arguments as strings, or lists or tuples of strings, not {args!r}"
        )
    return argv


def _build_env(env: Mapping[str, str | None]) -> dict[str, str] | None:
    if not env:
        return None
    merged = dict(os.environ)
    for key, value in env.items():
        name = key.upper() if sys.platform == "win32" else key
        if value is None:
            merged.pop(name, None)
        else:
            merged[name] = value
    return merged


def _resolve_program(caller: str, program: str, root: str, env: dict[str, str] | None) -> str:
    import shutil

    search_path = None if env is None else env.get("PATH", os.defpath)
    has_separator = "/" in program or os.sep in program
    resolved = (
        shutil.which(os.path.join(root, program))
        if has_separator
        else shutil.which(program, path=search_path)
    )
    if resolved is None:
        where = "relative to the root" if has_separator else "on PATH"
        raise FileNotFoundError(
            errno.ENOENT, f"{caller} found no program {program!r} {where}", program
        )
    return os.path.abspath(resolved)


def _spawn(
    context: Context,
    argv: list[str],
    *,
    cwd: str | None,
    env: dict[str, str] | None,
    stdin: _Stream,
    stdout: _Stream,
    stderr: _Stream,
    timeout: float | None,
    is_live: bool,
    is_task: bool,
) -> tuple[int, bytes, bytes]:
    """Run `argv` to its end and return its exit status with what it wrote to a captured stdout and stderr, raising KeyboardInterrupt where the invocation ended it."""
    import subprocess

    commands = context.commands
    if is_live:
        sys.stdout.flush()
        sys.stderr.flush()
    # A session of its own has no terminal to prompt on, and killing it whole closes the pipes a surviving grandchild would hold open.
    in_session = not is_live and sys.platform != "win32"
    # A process group of its own keeps the console's CTRL_BREAK_EVENT, a graceful stop, from ending a rule's command.
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" and not is_live else 0
    )
    reader = None
    terminal = None
    if stderr == subprocess.PIPE and context.window_size is not None and sys.platform != "win32":
        reader, terminal = _open_terminal(context.window_size)
        stderr = terminal
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            start_new_session=in_session,
            creationflags=creationflags,
        )
    except BaseException:
        if reader is not None:
            reader.close()
        raise
    finally:
        if terminal is not None:
            os.close(terminal)
    if reader is not None:
        reader.start()
    is_added = commands.try_add(process, in_session, is_task)
    try:
        with process:
            if not is_added:
                _kill(process, in_session)
            try:
                out, err = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                _kill(process, in_session)
                error.output, error.stderr = process.communicate()
                if reader is not None:
                    error.stderr = reader.join()
                raise
            except BaseException:
                _kill(process, in_session)
                raise
    finally:
        commands.remove(process)
    if reader is not None:
        err = reader.join()
    if commands.is_ended(is_task):
        raise KeyboardInterrupt
    returncode = process.returncode
    assert isinstance(returncode, int)
    return returncode, out or b"", err or b""


class _TerminalReader:
    """Reads everything written to a pseudo-terminal, from the end its commands don't hold."""

    def __init__(self, descriptor: int) -> None:
        self._descriptor = descriptor
        self._chunks: list[bytes] = []
        self._thread = threading.Thread(target=self._read, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self) -> bytes:
        """Wait until every process closed the terminal, and return what they wrote."""
        self._thread.join()
        return b"".join(self._chunks)

    def close(self) -> None:
        """Close the terminal, unless reading started, which closes it as it ends."""
        if not self._thread.is_alive() and self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1

    def _read(self) -> None:
        try:
            while True:
                try:
                    chunk = os.read(self._descriptor, _READ_BYTES)
                except OSError:
                    # Linux raises EIO once every command closed its end.
                    return
                if not chunk:
                    return
                self._chunks.append(chunk)
        finally:
            os.close(self._descriptor)
            self._descriptor = -1


if sys.platform != "win32":

    def _open_terminal(window_size: tuple[int, int]) -> tuple[_TerminalReader, int]:
        """Return a reader of a new pseudo-terminal `window_size` rows by columns, and the end of it a command writes to, which the caller closes."""
        # Imported here, since only a terminal needs it.
        import termios

        # Both libc's openpty and Python's fallback open the terminal's end with O_NOCTTY on Linux, and other systems
        # make a terminal the controlling one only on request, so a command never gets one to prompt on.
        primary, terminal = os.openpty()
        reader = _TerminalReader(primary)
        try:
            attributes = termios.tcgetattr(terminal)
            # Without output processing, the kernel leaves each newline as the command wrote it.
            attributes[1] &= ~termios.OPOST
            termios.tcsetattr(terminal, termios.TCSANOW, attributes)
            termios.tcsetwinsize(terminal, window_size)
        except BaseException:
            reader.close()
            os.close(terminal)
            raise
        return reader, terminal


def _send_kill(process: subprocess.Popen[bytes], in_session: bool) -> None:
    # in_session already excludes Windows, but ty needs the platform check to accept os.killpg there.
    if sys.platform == "win32" or not in_session:
        with contextlib.suppress(OSError):
            process.kill()
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)


def _kill(process: subprocess.Popen[bytes], in_session: bool) -> None:
    _send_kill(process, in_session)
    # Popen.__exit__ waits only briefly after an interrupt, which would leave the killed command unreaped.
    process.wait()
