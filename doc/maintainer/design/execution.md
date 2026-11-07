# Execution

## Commands

`fac.run` spawns its arguments directly, never through a shell, so nothing needs quoting and nothing differs between platforms' shells. A spawn costs about a millisecond on Linux and several on Windows, against tens to hundreds of milliseconds per compile.

A rule's command runs in a session of its own with no terminal and an empty stdin, unless `stdin=` names a file, so a command that would prompt, such as `sudo` asking for a password, fails at once instead of waiting behind captured output. sudo caches a password per terminal, so a command needing it relies on a sudoers entry that asks for none. A task's commands, and those of a rule with `terminal=True`, run in Facere's foreground process group with the terminal instead, so they can prompt and an interrupt reaches them directly. A task's command with `quiet=True` runs as a rule's does, since its output is captured too.

When Facere's own stderr is a terminal, a rule's command gets a pseudo-terminal as its stderr instead of a pipe, so a compiler colours its diagnostics as it would unwrapped. Its stdout stays a pipe, so what a recipe reads from it never depends on whether Facere had a terminal, and its stdin stays empty. Facere opens the pty's terminal end with `O_NOCTTY`, so it never becomes the command's controlling terminal and a prompt still fails at once, and clears `OPOST` on it, so the kernel's newline translation leaves the output unaltered. The pty takes Facere's window size, so a tool that wraps diagnostics wraps them as it would unwrapped. Facere reads the other end into the same capture the pipe would fill, printed whole when the rule finishes, and treats `EIO` there, which Linux returns once the command closes its end, as end of output. A recipe that passes `stderr=` gets its file, as always. Windows has no stderr-only pseudo-terminal, since ConPTY replaces a process's whole console, so there a rule's stderr stays a pipe.

## Environment

Every command inherits Facere's own environment, so a task's debugger, pager, or serial monitor sees the terminal's `TERM`, a GUI sees the display, and git sees the SSH agent. None of it joins the fingerprint, so opening a new shell re-executes nothing. A variable that changes an output is written in Python instead, through `env=` for one command or `fac.env(**values)` for every command. Any `fac.py` may call `fac.env`, and every call applies project-wide, so calls may repeat a variable's value but never change it: one that does fails collection, naming both calls, rather than letting whichever loads last silently win.

Where a tool's own setup script computes variables the tool requires, as Visual Studio's does, a rule runs that script and records the variables in a file every consumer inputs and relays through `env=`, so they are fingerprinted by content and do not depend on the shell `fac` started in.

## Package-managed tools

A tool a package manager installs, such as pytest in a uv project, runs through the manager's command that syncs the environment before running, as in `fac.run("uv", "run", "--locked", "pytest")`, and its rule inputs the lockfile. The environment then matches the lockfile whenever the rule executes, even after a task rewrote the lockfile earlier in the same invocation. A manager without such a command gets an install rule that records what it installed, as [best practices](../../user/7-best-practices.md#stamp-files) shows for npm, and the tool's rules input that record.

## Scheduling

- **Jobs.** Declared outputs make parallel execution safe, so the default is every CPU the process may use: its affinity set where the OS exposes one, else `os.cpu_count()`, capped by a cgroup CPU quota so CI containers do not oversubscribe. Workers are threads, since a command releases the GIL while its process runs, so a recipe doing heavy Python computation spawns a subprocess for it. A tool that runs its own workers, such as `pytest -n` or a parallel link, gets an explicit count from its recipe, and `max_jobs` or a shared semaphore keeps such rules from overlapping, as in ninja.
- **Ordering.** Targets are built batch by batch in the order the requirements set out. GNU make processes goals in order only without `-j` and races with it, which the Linux kernel's Makefile works around by running one `make` per goal.
- **Existing outputs.** Facere leaves an existing output in place when its rule executes, since most tools, compilers included, overwrite theirs, and deleting thousands of object files first would buy nothing.

## Failure

The first failure stops new jobs, running jobs finish, and Facere exits with status 1, as it does when a store's method raises, since a store's code is the project's own. `-k` instead builds everything not downstream of a failure. An interrupt kills every running command's session, since a command in a session of its own never sees the terminal's `SIGINT`. SIGTERM on Linux and macOS, and `CTRL_BREAK_EVENT` on Windows, ask for a graceful stop instead: no new job starts, running rules finish, their stores are written, and they are recorded, and a task's commands get the same signal, then are killed after 10 s. `kill`, `docker stop`, and a cancelled CI job therefore keep every finished compile, and a parent process can stop Facere without a terminal.

A failed or interrupted rule has its recorded fingerprint cleared and its outputs left as the recipe left them, so a half-written object file re-executes next time and stays available for inspection meanwhile.

## Output

Each rule's command output, stdout and stderr both, is captured and printed whole and unaltered when the rule finishes, so parallel output never interleaves, while `fac.run` still returns the stdout. A recipe's own Python output, such as `print()`, is captured per rule the same way. A task's output is shown live instead, and its failure report names the task and the failing command without repeating what was shown. A task's command with `quiet=True` has its output captured as a rule's is, so `fac.run` can return its stdout, though the command then writes to pipes rather than the terminal.

A failure prints the failing command or exception, its stderr and stdout, and the tail of any file its `stdout=` or `stderr=` filled, then names the rule and its `fac.py:line`.

On a terminal, one status line shows progress, paused while a task runs. When stdout is not a terminal, Facere prints no colour and no status line. With `-C`, and around the shown output of a rule whose command used `cwd=`, Facere prints `fac: Entering directory '<absolute path>'` and a matching `fac: Leaving directory` line, as make does, so relative paths in a tool's diagnostics resolve. The warning that assertions are disabled, through `-O` or `PYTHONOPTIMIZE`, is one line.
