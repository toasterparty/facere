# Command line

| Usage | Effect |
|---|---|
| `fac [TARGET...] [-- ARG...]` | Build the targets, in the order given, passing every `ARG` to each task they reach that takes `fac.Args`, which at least one must when an `ARG` is given. With no targets, the root's defaults, and `--` is an error. With no defaults, every rule and no task, which for a project with no rules succeeds, doing nothing |
| `-C DIR` | Run as if started in `DIR`, which becomes the root, framing the invocation's output with `fac: Entering directory` and `fac: Leaving directory` lines |
| `-j N`, `--jobs N` | Parallel jobs, or `auto`, the default, for all usable CPUs |
| `-k`, `--keep-going` | Continue past failures |
| `-q`, `--quiet` | Hide the output of every successful command a rule runs |
| `-v`, `--verbose` | Print each command as it runs, and for each rule that executes, name why: `code`, `values`, `inputs`, `added-inputs`, `outputs`, `always`, or `first-run`, one word each since `--json` reports them as values, with what changed, such as `cflags` |
| `--check [TARGET...]` | Validate collection, confirm that every source exists, and print each stale rule with its reason, then each rule that may execute once a stale rule upstream of it does, naming those stale rules. Executes no recipe, and exits non-zero only on an error |
| `--list [TARGET...]` | Rules and tasks with their docstrings and defaults, or what each target resolves to. Collection validates the whole tree first, so `fac --list` checks a fresh clone without executing a recipe. A task taking `fac.Args` shows as `NAME -- ARGS`, with its docstring saying what they mean |
| `--inputs TARGET...`, `--outputs TARGET...` | Print the absolute path of every input, or every output, of the targets' rules, one per line, in target order. Inputs are those the rules declare plus those their last execution reported. A `FileStore`'s path prints once for all its virtual outputs, and virtual outputs of other stores print nothing. A task has none. Builds nothing and executes no recipe, so a script builds first: `fac app && "$(fac --outputs app)"`. It fails on a target that resolves to nothing |
| `--json` | With `--list`, `--check`, or `--timings`, emit JSON instead of text, as [below](#json). With any other mode it is an error |
| `--timings` | After the invocation, print to stderr where its time went: interpreter start, each `fac.py`'s collection with its slowest imports, hashing with its stat and hash counts, state reads and commits, each rule's and task's duration, and the critical path. With `--json` too, since stdout belongs to the build's commands |
| `--lock-timeout SECONDS` | Fail instead of waiting longer than `SECONDS` for another invocation on the same output directory, where `0` fails at once. Without it, Facere waits as long as it takes |
| `--out DIR` | Output directory, relative to the root, inside it or not, default `build` |
| `--docs` | Print the directory holding the running Facere's docs |
| `--python` | Print the interpreter Facere runs on, for an editor reading `fac.py` files |
| `--version` | Print Facere's version |

`fac --help` is the only user documentation of the flags a release supports, so this table may run ahead of it. A mode flag takes no operand, so `fac --check app` and `fac app --check` are the same by construction. `--list`, `--check`, `--inputs`, and `--outputs` contradict one another, so any two together fail. With every configuration in one graph, `fac '*.debug' '*.release'` builds two in one parallel batch, and `fac build/` builds every one. `--out` moves the whole output directory, for a CI job that wants its own.

On a POSIX terminal, Facere sets the scroll region to every row but the last and draws `[position/total] label` there with save-cursor and restore-cursor, so commands keep writing straight to the terminal and see it unwrapped. The position counts every rule and task reached, executed or not, against the number reachable from the targets. SIGWINCH redraws the row, and it is erased however the invocation ends, a graceful stop and SIGHUP included, before the closing line. A command that takes over the whole screen, or a multiplexer that drops lines scrolled out of a partial region from its scrollback, can spoil the row. Windows has no row until its console is switched to VT processing.

## Exit statuses

| Status | Outcome |
|---|---|
| `0` | Success |
| `1` | A recipe failed, a store's method raised, or a damage check or a store's round-trip check failed, each the project's own code or files |
| `2` | Facere could not start the build: bad arguments, an error in a `fac.py`, or a target that resolves to nothing |
| `3` | `--lock-timeout` expired, which a caller with a deadline retries, unlike a broken definition |
| `4` | Facere itself raised, a bug, printed with its traceback, so it is never taken for a failed recipe |
| `130` | An interrupt, as a shell reports a process that `SIGINT` killed |
| `143` | A graceful stop, on every OS, so a supervisor tells a child it stopped from one that failed |

Every other status is reserved, since a status cannot be split once a caller branches on it. A task's command status is not passed through, and `--check` exits `0` with stale rules, which `--json` reports. Either can gain a flag later.

## Contract

A caller may parse:

- the exit status
- each line `--inputs` and `--outputs` print
- the documented keys of `--json` from `--list` and `--check`
- diagnostics, as `<location>: <severity>: <text>`, where the location is `path:line:column` or `fac` and the severity is `error`, `warning`, or `note`
- the `fac: Entering directory` and `fac: Leaving directory` lines, and watch mode's `fac: change in` line
- the closing line's first word, `Finished`, `Failed`, `Stopped`, or `Interrupted`, which every invocation that parsed its arguments ends on, `Failed` for each status from `1` to `4`

Everything else may change in any release: the text of any message, the rest of the closing line, the status row, `--list` and `--check` as text, `-v`, and all of `--timings`, JSON included, since its phases are Facere's internals.

## JSON

`--list` and `--check` print one object, `{"root": "/abs", "out": "build", "records": [...]}`, so keys can be added beside the records, with every other path relative to the root. Each record holds:

- `id`, the target string that builds exactly that record and works on the command line: an output path for a rule, the dotted name for a task, `page[about]` for a virtual output, since a name such as `page` covers every page
- `name`, `kind` (`rule` or `task`), `doc`, and `default`
- `location` as `{"file", "line", "column"}`, so a script parses no prose
- `inputs`, each with its kind, `input`, `order-only`, or `added`, since they go stale differently, and `outputs`, each virtual output with its store and key. A key is any hashable value, so it prints as its `repr` beside the `id`
- for `--check`, `stale`, a list of `{"reason", "detail"}` whose `reason` is one of the `-v` reasons, and `after`, the ids of the stale rules upstream whose execution would make the record's rule execute

A consumer ignores unknown keys and unknown `kind` and `reason` values, which makes adding them no break.
