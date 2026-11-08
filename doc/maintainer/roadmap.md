# Roadmap

| Release | Contents |
|---|---|
| 0.x | Phase 1, the core in [`design/`](./design/README.md), then phase 2, the shipped extensions `facere.c`, `facere.fetch`, `facere.git`, and `facere.uv`. Any interface may break |
| 1.0 | Both phases, the shipped docs, CI on Linux and Windows, and both no-op benchmarks within their 300 ms budget. The compatibility promise starts here |
| After 1.0 | [Watch mode](./design/watch.md), the fuller `--check` below, MSVC in `facere.c`, a `dyndep`-like mechanism for dependencies known only after a scan, and a compiled hot path once a profile names one |

## Next

Implement a terminal for rules' commands before any new interface. A rule's command gets a pipe on stderr, so a compiler drops its colour under Facere, against the principle that a tool behaves as it does from the shell. [Execution](./design/execution.md) designs the pseudo-terminal.

## Phase 1 milestones

A proposal, ordered to rough in the whole path first. Each ends with its tests passing on Linux and Windows.

1. **Correctness.** The hash cache and the damage checks.
2. **Scheduling.** Parallel jobs, `max_jobs`, failure and `-k`, interrupt and graceful stop, the lock and `--lock-timeout`, `fac.give_lock()`, and the terminal for tasks.
3. **Stores.** `fac.Virtual`, `fac.VirtualInput`, `fac.VirtualOutput`, `fac.read` and `fac.write`, `fac.FileStore`, virtual output records and stamps in the state, the flush and its round-trip check, and file outputs moved onto the same code path as the built-in store.
4. **Names.** Scopes, groups, patterns, `::`, `--list`, `--check`, `--paths`, `--json`, and `-v` reasons.
5. **Budget.** `--timings`, the CI benchmarks, the C project's and the single-file store's, and the Windows benchmark.
6. **Distribution.** Shipped docs and their CI checks, `--docs`, and `--python`.

Phase 2 then adds the four extensions and the example projects, each project with a table of edits and the rules each one executes, which become its tests. Each extension gets the check that it imports only `facere.__all__`. `facere.c` has that check already, and so far holds only `makefile_deps`.

## Open decisions

- **Typed task options.** A task declaring `count: int = 1500`, filled from the command line, would replace the `argparse` that the `many-files` and `many-rows` examples need for one option. Open: the command-line syntax beside `--`, which types convert, and what `--help` shows.
- **`inherit=` on `fac.run`.** The `python-app` example passes `inherit=True` and `inherit=[names]`, but no design defines it, and [execution](./design/execution.md) has every command inherit the whole environment. Decide whether a command's environment can be narrowed, then give it one parameter that takes one type.
- **Configurations without nesting.** The `c-server-client` example defines rules inside `for` loops nested in `fac.scope` blocks, the most advanced Python any example needs. A form that loops for the author, such as a configuration table given to one call, would keep configurations within beginner Python.
- **Unscheduled helpers.** `@fac.rule(clear=True)` and `fac.write_archive` are designed in [the `fac.py` interface](./design/fac-py.md) but in no milestone.
- **Directory inputs holding other rules' outputs.** A rule inputting `src` while another rule outputs `src/gen.c` is not ordered after that rule, since collection orders only by exact path. The undeclared-path check and `fac.add_inputs` also treat everything inside a declared directory as declared, so the ordering check never sees the file. Open: order the reader after every rule outputting inside its directory, reject such an input, or run both checks on those paths.
- **Colour on Windows.** A rule's stderr stays a pipe there, so tools that colour only on a console print plain diagnostics. A tool flag such as `-fdiagnostics-color=always`, set by the project, is the workaround until a mechanism exists.
- **A fuller `--check`**, after 1.0, enforcing best practices Facere now only documents. What holds for every project stays an error in every invocation, as cycles and two rules outputting one path are, so this holds only what some project may do on purpose, and what must watch a recipe executes as a flag on a real build:
    - fail a recipe that reads `os.environ`
    - fail a recipe that spawns a process other than through `fac.run`, from the audit hook's `subprocess.Popen` event, since such a program escapes `-v` and the undeclared-path check
    - audit collection for reads of rule outputs and for network access
    - list orphaned outputs and virtual outputs. Deleting them stays the user's, through deleting the output directory
    - `-ffile-prefix-map` and `ar D` in `facere.c`
    - narrow the scratch-file exemption
    - an opt-in determinism check
- **Stores**, beyond [the design](./design/stores.md):
    - a source store for the `many-rows` example's table, so each rule inputs its own row instead of the table being read during collection, and a missing table stops meaning revision 0
    - rules defined from a store's own keys, such as one per row the table holds, which would read the store during collection and belongs with the `dyndep`-like mechanism after 1.0
    - tasks declaring `fac.VirtualInput` and calling `fac.read`, as a deploy check reading a published page would
    - watch mode polling a remote store's `stamp` on an interval set in Python, opt-in per store since each poll is a request
