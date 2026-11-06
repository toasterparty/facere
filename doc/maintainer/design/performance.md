# Performance

Two CI benchmarks, the C project and 10000 rules writing one `FileStore`, enforce the [requirements](../requirements.md)' 300 ms budget for an invocation with nothing stale by reading `--timings --json`, so a regression names the phase that grew. Shared runners are noisier than the N100 the budget was measured on, so CI compares each phase against its share of the budget, with headroom.

The parts, measured on an Intel N100 under Python 3.11, total about 100 ms before the project's own code:

| Phase | Cost |
|---|---|
| Interpreter start | 14 ms |
| Facere's imports, `sqlite3`, `ast`, `dataclasses`, and `typing` among them, with `json`, `subprocess`, and `tomllib` deferred until an invocation needs them | 32 ms |
| Listing the tree, a stat per directory against its cached listing | under 1 ms |
| Executing the `fac.py` files, defining and validating 1000 rules, globbing the cached listings | 3 ms, plus the project's own code |
| Hashing syntax trees and values | 6 ms |
| Reading the state | 3 ms |
| 7000 stats against the hash cache, outputs included | 22 ms |
| 1000 fingerprints, 30 added inputs each | 17 ms |

The audit hook and the argument check cost nothing here, since they act only while a recipe executes, and the shadowing check for added inputs runs only when the listing shows new files. Most of the rest is interpreter startup, imports, and system calls, which compiling Facere's core would not speed up, so a compiled CPython extension waits for a profile of the benchmark to name a hot path. Check `python -X importtime -m facere --list` against the import budget before splitting a module. Windows also gets an early benchmark of a full build, since slower process creation and antivirus scanning of new files could dominate there.

The benchmark's generator is a shared module, so editing it regenerates the project. Its rule outputs the project as one directory output, and the timed invocation uses `-C` into it with `--out` outside it, since writing inside the generator's directory output would fail the end-of-invocation damage check.

## Open risks

- **Module-level code**, such as a probe of a tool's `--version`, counts against the budget, where a rule recording it would not.
- **Large directory outputs** cost one stat per file on every invocation. A `FileStore` costs one stat for any number of virtual outputs.
- **Remote stores** cost one `stamp` request per no-op, or a full `read` for a store with no stamp, which counts against the project's budget, not Facere's.
