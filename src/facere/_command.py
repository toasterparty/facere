"""fac.run, which spawns one command from a recipe."""

import contextlib
import errno
import os
import shlex
import shutil
import signal
import subprocess
import sys
from collections.abc import Mapping
from typing import IO, TextIO

from facere._context import Running, get_context

_Stream = int | IO[bytes] | None


def run(
    *args: str | list[str] | tuple[str, ...],
    cwd: str | None = None,
    env: Mapping[str, str | None] | None = None,
    stdin: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    timeout: float | None = None,
    quiet: bool = False,
) -> str:
    """Run one command without a shell and return its stdout decoded as UTF-8, raising subprocess.CalledProcessError on a non-zero exit.

    Each of `args` is one string, or a list or tuple of strings that contributes each of its items in order, so `fac.run(CC, CFLAGS, "-c", source)` needs no `*`. The first string is the program, the rest its arguments. The program resolves through `PATH`, or against the root when it contains a separator, and raises FileNotFoundError when it doesn't resolve. The command inherits Facere's environment, with what `fac.env` set over it, then `env` over both, where `None` unsets a variable. `cwd` is relative to the root. `stdin`, `stdout`, and `stderr` name files, relative to the root, to feed the command and fill, and a file both `stdout` and `stderr` name receives both streams. In a rule, the command reads an empty stdin unless `stdin` names a file, and its output is captured. On success it is printed whole unless `quiet` is true, and on failure it travels in the raised error, which Facere prints if it fails the recipe. In a task, the command shares Facere's standard streams, so its stdout is printed rather than returned. `timeout` kills the command after that many seconds and raises subprocess.TimeoutExpired.
    """
    context = get_context("fac.run")
    if context.running is None:
        raise RuntimeError("fac.run runs a command only from the recipe of a rule or task")
    argv = _flatten(args)
    if context.is_verbose:
        print(shlex.join(argv), file=sys.stderr, flush=True)
    command_env = _build_env({**context.env, **(env or {})})
    program = _resolve_program(argv[0], context.root, command_env)
    in_rule = context.running is Running.RULE
    captured = subprocess.PIPE if in_rule else None
    with contextlib.ExitStack() as files:
        stdin_stream: _Stream = subprocess.DEVNULL if in_rule else None
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
            returncode, out, err = _spawn(
                [program, *argv[1:]],
                cwd=cwd,
                env=command_env,
                stdin=stdin_stream,
                stdout=stdout_stream,
                stderr=stderr_stream,
                timeout=timeout,
                in_rule=in_rule,
            )
        except subprocess.TimeoutExpired as error:
            # Without pipes, communicate() reports the time remaining, not the limit set.
            assert timeout is not None
            raise subprocess.TimeoutExpired(argv, timeout, error.output, error.stderr) from None
    text = out.decode("utf-8", "surrogateescape")
    if returncode != 0:
        raise subprocess.CalledProcessError(
            returncode, argv, output=text, stderr=err.decode("utf-8", "surrogateescape")
        )
    if in_rule and not (quiet or context.is_quiet):
        write_output(err, out)
    return text


def write_output(err: bytes, out: bytes) -> None:
    """Write a command's captured output unaltered to Facere's own streams, stderr first."""
    _write_bytes(sys.stderr, err)
    _write_bytes(sys.stdout, out)


def _write_bytes(stream: TextIO, data: bytes) -> None:
    if not data:
        return
    stream.flush()
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        stream.write(data.decode("utf-8", "replace"))
        stream.flush()
        return
    buffer.write(data)
    buffer.flush()


def _is_same_path(path: str, other: str) -> bool:
    return os.path.normcase(os.path.normpath(path)) == os.path.normcase(os.path.normpath(other))


def _flatten(args: tuple[str | list[str] | tuple[str, ...], ...]) -> list[str]:
    argv = [item for arg in args for item in (arg if isinstance(arg, list | tuple) else [arg])]
    if not argv or not all(isinstance(item, str) for item in argv):
        raise TypeError(
            f"fac.run takes the program and its arguments as strings, or lists or tuples of strings, not {args!r}"
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


def _resolve_program(program: str, root: str, env: dict[str, str] | None) -> str:
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
            errno.ENOENT, f"fac.run found no program {program!r} {where}", program
        )
    return os.path.abspath(resolved)


def _spawn(
    argv: list[str],
    *,
    cwd: str | None,
    env: dict[str, str] | None,
    stdin: _Stream,
    stdout: _Stream,
    stderr: _Stream,
    timeout: float | None,
    in_rule: bool,
) -> tuple[int, bytes, bytes]:
    if not in_rule:
        sys.stdout.flush()
        sys.stderr.flush()
    in_session = in_rule and sys.platform != "win32"
    with subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        start_new_session=in_session,
    ) as process:
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            _kill(process, in_session)
            error.output, error.stderr = process.communicate()
            raise
        except BaseException:
            _kill(process, in_session)
            raise
    returncode = process.returncode
    assert isinstance(returncode, int)
    return returncode, out or b"", err or b""


def _kill(process: subprocess.Popen[bytes], in_session: bool) -> None:
    # in_session already excludes Windows, but ty needs the platform check to accept os.killpg there.
    if sys.platform == "win32" or not in_session:
        process.kill()
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
    # Popen.__exit__ waits only briefly after an interrupt, which would leave the killed command unreaped.
    process.wait()
