# Command line

| Usage | Effect |
|---|---|
| `fac [TARGET...] [-- ARG...]` | Build the targets, in the order given, passing every `ARG` to each task they reach that takes `fac.Args`, which at least one must when an `ARG` is given. With no targets, the root's defaults, and `--` is an error. With no defaults, every rule and no task, which for a project with no rules succeeds, doing nothing |
| `-C DIR` | Run as if started in `DIR`, which becomes the root |
| `-j N`, `--jobs N` | Parallel jobs, or `auto`, the default, for all usable CPUs |
| `-k`, `--keep-going` | Continue past failures |
| `-q`, `--quiet` | Hide the output of every successful command a rule runs |
| `-v`, `--verbose` | Print each command as it runs, and for each rule that executes, name why: `code`, `values`, `inputs`, `added inputs`, `outputs`, `always`, or `first run`, with what changed, such as `cflags` |
| `--check [TARGET...]` | Validate collection, confirm that every source exists, and print each stale rule with its reason, then each rule that may execute once a stale rule upstream of it does, naming those stale rules. Executes no recipe, and exits non-zero only on an error |
| `--list [TARGET...]` | Rules and tasks with their docstrings and defaults, or what each target resolves to. Collection validates the whole tree first, so `fac --list` checks a fresh clone without executing a recipe. A task taking `fac.Args` shows as `NAME -- ARGS`, with its docstring saying what they mean |
| `--paths KIND TARGET...` | Print the absolute path of every input or output, as `KIND` (`inputs` or `outputs`) says, of the targets' rules, one per line, in target order. Inputs are those the rules declare plus those their last execution reported. A `FileStore`'s path prints once for all its virtual outputs, and virtual outputs of other stores print nothing. A task has none. Builds nothing and executes no recipe, so a script builds first: `fac app && "$(fac --paths outputs app)"`. It fails on a missing `KIND` or a target that resolves to nothing |
| `--json` | With `--list`, `--check`, or `--timings`, emit JSON instead of text. `--list` and `--check` share one record per target: `name`, `kind` (`rule` or `task`), `location` (`fac.py:line`), `doc`, `default`, `inputs`, and `outputs`, each virtual output listed with its store and key, plus, for `--check`, `stale`, the reasons the target is stale, and `after`, the stale rules upstream whose execution would make it execute. With any other mode it is an error |
| `--timings` | After the invocation, print where its time went: interpreter start, each `fac.py`'s collection with its slowest imports, hashing with its stat and hash counts, state reads and commits, each rule's and task's duration, and the critical path. |
| `--lock-timeout SECONDS` | Fail instead of waiting longer than `SECONDS` for another invocation on the same output directory, where `0` fails at once. Without it, Facere waits as long as it takes |
| `--out DIR` | Output directory, relative to the root, inside it or not, default `build` |
| `--docs` | Print the directory holding the running Facere's docs |
| `--python` | Print the interpreter Facere runs on, for an editor reading `fac.py` files |
| `--version` | Print Facere's version |

`fac --help` is the only user documentation of the flags a release supports, so this table may run ahead of it. `fac.main(args)` takes the same arguments and returns the exit status, so the Python API has nothing of its own to document. `--list`, `--check`, and `--paths` contradict one another, so any two together fail. With every configuration in one graph, `fac '*.debug' '*.release'` builds two in one parallel batch, and `fac build/` builds every one. `--out` moves the whole output directory, for a CI job that wants its own.

The exit status is `0` on success, `1` when a recipe fails, and `2` when Facere could not start the build: bad arguments, an error in a `fac.py`, a target that resolves to nothing, or a lock timeout. A caller therefore knows whether its own code or the build definition is wrong. An interrupt exits with `130`, as a shell reports a process that `SIGINT` killed.

On a POSIX terminal, Facere sets the scroll region to every row but the last and draws `[position/total] label` there with save-cursor and restore-cursor, so commands keep writing straight to the terminal and see it unwrapped. The position counts every rule and task reached, executed or not, against the number reachable from the targets. SIGWINCH redraws the row, and SIGTERM and SIGHUP erase it before the signal takes its default action. A command that takes over the whole screen, or a multiplexer that drops lines scrolled out of a partial region from its scrollback, can spoil the row. Windows has no row until its console is switched to VT processing.
