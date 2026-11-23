# Windows

What running, testing, and debugging Facere natively on Windows teaches, beyond what [execution](./design/execution.md) and [state](./design/state.md) design.

## Processes and signals

- A uv environment's `.venv\Scripts\python.exe` is a launcher that runs the real interpreter as its child, so `Popen(...).pid` is the launcher's PID, not the one Facere writes to `build/.fac/lock.pid`. Killing the launcher with `terminate()` or `kill()` takes the interpreter with it.
- `terminate()` is TerminateProcess: Facere gets no graceful stop and leaves its task's commands running, and the orphan holds its test directory open, so the next run in the same basetemp errors in teardown with `WinError 32`. A test that stops `fac` starts it with `CREATE_NEW_PROCESS_GROUP` and sends `CTRL_BREAK_EVENT`.
- A test that fails before its `fac` ends, a mutant run especially, leaves that `fac` and its commands running after pytest exits. List and kill them with `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` before the next run. Leaked processes also slow the whole suite severalfold.
- `os.kill(pid, 0)` terminates the process. Probe liveness with `OpenProcess` plus `GetExitCodeProcess` against `STILL_ACTIVE` (259).
- CPython runs a Python-level SIGBREAK handler only when the main thread next executes bytecode, and `Event.wait(timeout)` is not interrupted by SIGBREAK, so Facere sees a `CTRL_BREAK_EVENT` up to `WAKE_S` late. A worker meanwhile starts the next rule on its own, so a test that creates `go` right after the break races. `test/cli/test_stop/break_rule/fac.py` waits on the installed handler's `__self__.is_stop_requested` to order it.
- A task's command killed by the console's `CTRL_BREAK_EVENT` exits `0xC000013A` (3221225786). The venv launcher survives the break and passes the child's status through.
- `SetConsoleCtrlHandler(None, True)` is inherited by children created after it, so a Ctrl-C driver sets it only after starting `fac`. A driver in `CREATE_NEW_CONSOLE` running `GenerateConsoleCtrlEvent(0, 0)` works from pytest, flashing a console window.
- Git Bash, which CI's `shell: bash` runs, starts native programs with Ctrl-C ignored, and every descendant inherits that, `CREATE_NEW_CONSOLE` included. A Ctrl-C driver therefore calls `SetConsoleCtrlHandler(None, False)` before starting `fac`, or `fac` never sees the event and the test fails at its deadline from Git Bash while passing from PowerShell.

## Consoles

- `os.isatty` holds for `NUL`, since the CRT counts any character device, so a rule's command with `DEVNULL` stdin reads `isatty(0) == True`. Tell a console by `GetConsoleMode` on `msvcrt.get_osfhandle(fd)`.
- A rule's command gets no console even when Facere runs in one, as starting `uv run fac -C` with `CREATE_NEW_CONSOLE` shows.

## The lock

- A named mutex is destroyed with its last handle, so after its holder is killed the next invocation creates a fresh one and never sees `WAIT_ABANDONED`. That return happens only if another handle was open across the kill, which `test_lock_whose_holder_was_killed_is_taken_by_the_next_invocation` arranges with `OpenMutexW`.
- A thread that gets `WAIT_ABANDONED` owns the mutex, and waiting again from the same thread nests the ownership.

## Files and messages

- `os.stat`'s `st_ctime_ns` is the creation time on Windows, through Python 3.15 at least, so no rewrite moves it, and two files created in one timer tick share it for good. A test reads the change time the hash cache uses through `facere._filesystem.read_change_time_ns`. A loop waiting for a rewrite's `st_ctime_ns` to pass another file's once spun until CI's job timeout.
- An `OSError`'s message shows its filename with `repr`, so backslashes appear doubled in messages. Build expected text with `{str(path)!r}`.
- PowerShell's `Set-Content` and `Add-Content` write CRLF, which `.gitattributes` (`eol=lf`) flags. Write files with `[IO.File]::WriteAllText` or an editor.
