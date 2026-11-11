# Roadmap

| Release | Contents |
|---|---|
| 0.x | Phase 1, the core in [`design/`](./design/README.md) with [watch mode](./design/watch.md), then phase 2, the shipped extensions `facere.fetch`, `facere.git`, and `facere.uv`. Any interface may break |
| 1.0 | Both phases, CI on Linux and Windows, both no-op benchmarks within their 300 ms budget, and shipped docs that describe exactly what 1.0 does and mark nothing planned. The docs pass when, judged by hand, an agent given only the installed package writes a correct `fac.py`. The compatibility promise starts here, and never ends: there is no 2.0 |
| After 1.0 | [`facere.c`](./design/extensions/c.md), MSVC in it, the fuller `--check` below, a `dyndep`-like mechanism for dependencies known only after a scan, and a compiled hot path once a profile names one |

## Next

Correctness, the first milestone below, before any other.

## Phase 1 milestones

A proposal, ordered to rough in the whole path first. Each ends with its tests passing on Linux and Windows.

1. **Correctness.** The hash cache and the damage checks.
2. **Scheduling.** Parallel jobs, `max_jobs`, failure and `-k`, interrupt and graceful stop, the lock and `--lock-timeout`, `fac.give_lock()`, the terminal for tasks, and the pseudo-terminal for rules' commands, so a compiler keeps its color. The `serve` task in the `my-site` example calls `fac.give_lock()` once it exists, so `fac` in a second terminal does not wait on it.
3. **Watch mode.** The set of paths a cycle observed, then [the supervisor](./design/watch.md).
4. **Stores.** `fac.Virtual`, `fac.VirtualInput`, `fac.VirtualOutput`, `fac.read` and `fac.write`, `fac.FileStore`, virtual output records and stamps in the state, the flush and its round-trip check, and file outputs moved onto the same code path as the built-in store.
5. **Names.** Scopes, groups, patterns, `::`, `--list`, `--check`, `--paths`, `--json`, and `-v` reasons.
6. **Budget.** `--timings`, the CI benchmarks, the C project's and the single-file store's, and the Windows benchmark. Measure what hashing the executable bit costs a project that never sets one: past a measurable share of the no-op, drop it or make it opt-in, off by default.
7. **Distribution.** Shipped docs and their CI checks, `--docs`, and `--python`.

Phase 2 then adds the three extensions and the example projects, each project with comments naming what an edit executes, and tests that check those claims. Each extension gets the check that it imports only `facere.__all__`.

## Open decisions

- **Typed task options.** A task declaring `count: int = 1500`, filled from the command line, would replace the `argparse` that the `many-files` and `many-rows` examples need for one option. Open: the command-line syntax beside `--`, which types convert, and what `--help` shows.
- **`inherit=` on `fac.run`.** The `python-app` example passes `inherit=True` and `inherit=[names]`, but no design defines it, and [execution](./design/execution.md) has every command inherit the whole environment. Decide whether a command's environment can be narrowed, then give it one parameter that takes one type.
- **Configurations without nesting.** The `c-server-client` example defines rules inside `for` loops nested in `fac.scope` blocks, the most advanced Python any example needs. A form that loops for the author, such as a configuration table given to one call, would keep configurations within beginner Python.
- **Unscheduled design.** These are designed but in no milestone:
    - in [the `fac.py` interface](./design/fac-py.md): `@fac.override`, `fac.rules`, `fac.from_root` and `fac.root`, `@fac.rule(always=True)` and `clear=True`, `fac.load` and `fac.save`, and `fac.write_archive`
    - in [collection](./design/collection.md): loading the other `fac.py` files under the root, `fac.exclude`, the cached directory listings, failing an output inside another rule's directory output, and the hint to filter a `fac.sources` list that holds a rule's output, which today fails the next invocation as a cycle
- **Color on Windows.** A rule's stderr stays a pipe there, so tools that color only on a console print plain diagnostics. A tool flag such as `-fdiagnostics-color=always`, set by the project, is the workaround until a mechanism exists.
- **A fuller `--check`**, after 1.0, enforcing best practices Facere now only documents. What holds for every project stays an error in every invocation, as cycles and two rules outputting one path are, so this holds only what some project may do on purpose, and what must watch a recipe executes as a flag on a real build:
    - fail a recipe that reads `os.environ`
    - fail a recipe that spawns a process other than through `fac.run`, from the audit hook's `subprocess.Popen` event, since such a program escapes `-v` and the undeclared-path check
    - audit collection for reads of rule outputs and for network access
    - list orphaned outputs and virtual outputs. Deleting them stays the user's, through deleting the output directory
    - report a rule stale again right after its own execution, such as one whose tool rewrites its own input, which never settles
    - `-ffile-prefix-map` and `ar D` in `facere.c`
    - narrow the scratch-file exemption
    - an opt-in determinism check
- **Stores**, beyond [the design](./design/stores.md):
    - a source store for the `many-rows` example's table, so each rule inputs its own row instead of the table being read during collection, and a missing table stops meaning revision 0
    - rules defined from a store's own keys, such as one per row the table holds, which would read the store during collection and belongs with the `dyndep`-like mechanism after 1.0
    - tasks declaring `fac.VirtualInput` and calling `fac.read`, as a deploy check reading a published page would
    - watch mode polling a remote store's `stamp` on an interval set in Python, opt-in per store since each poll is a request
