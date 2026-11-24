# The differential oracle

`test/oracle/` holds a Hypothesis state machine that edits a generated project and checks each incremental build against a build into a fresh output directory. `fac test` runs one fixed seed, and `fac test -- --long` adds eight shards on new seeds.

## Triage

- Run it on tmpfs while iterating: `uv run --locked pytest test/oracle --long --basetemp=/tmp/facere-oracle`. The long run takes about eight minutes on four cores.
- A failure shrinks for up to five minutes before it prints, longer under `build/`. Hypothesis then prints the steps, and the assertion names the rows that were stale with the fact that changed for each, the edits in plain words, and the project's directory, which keeps the last example Hypothesis ran, the shrunk one.
- `--hypothesis-seed=N` repeats a long-run failure on any shard, so add `-k "[0]" -n0`.
- A shrunk failure can be a different one from the failure first found. Where it ends in the test's own code, such as a `FileNotFoundError` from an edit, fix the edit's precondition and rerun the seed before reading it as Facere's.

## Mutants

`tools/oracle-mutants.py` swaps one exact string in `src/facere/` at a time for a staleness bug, runs the oracle against it, and reports each mutant as caught, missed, or unmatched. Rerun it after changing the family or what the machine expects, and update a mutant reported unmatched to the code as it now reads:

```sh
uv run tools/oracle-mutants.py --basetemp /tmp/facere-oracle-mutants --examples 300
```

- A mutant the family rarely exercises can pass 100 examples unnoticed, so rerun a miss with more examples before reading it as a hole.
- Collection hashes no code beyond a recipe and the function it wraps, which the family never decorates, so a mutant of a recipe's closure variables or `__wrapped__` is invisible to the oracle. `test/api/test_staleness.py` covers those.
- The family declares no task, so each invocation is one batch, and a mutant of what happens between batches, such as whether a failure lets the next batch start, is invisible to the oracle.
- The script rewrites files under `src/facere/` while it runs and restores each, so run it in a copy of the tree, such as `rsync -a --exclude .venv --exclude build` makes, wherever anything else may use the tree meanwhile.

## What the machine expects

- `Project.calc_rows` lists, per rule, the facts its fingerprint should hold. A fingerprint holds only a recipe's own code, so `_apply` raises the project's epoch, as a person editing a helper would, whenever an edit changes `Project.calc_helper_facts`, what the helpers a recipe calls add to its output. A build must execute exactly the rows whose facts differ from their record, so a new feature in the family needs both its rendering and its fact, or the oracle reports overbuilding.
- An output's bytes show every fact through the tags each function appends, so a missed fact shows as stale bytes too. Keep that property when adding a function.
- Hypothesis draws the first item of a pool far more often than the rest, and tries the rule that sorts first, by argument count then name, most. An edit that leaves the files as they were costs a step and checks nothing, which is why `INITIAL_TEXT` is outside `TEXTS`, and why `VALUES` and `ENVS` start with a member the project does not start with. Keep a new pool's first member an edit that changes something.
- `_forget_records` mirrors what an invocation forgets before building: records of rules no longer declared, and records naming a file name that a new file or a new output has.
- Removing a generated header also deletes the file a build left, since a project where `compile` never names its order-only parameter searches the generated directory and would read the orphan, which a fresh build lacks.
- `compile` and `link` fail where a file they read holds `FAIL_TEXT`, printing `failed` before raising, as they print `ran` after succeeding. A build where one fails executes nothing downstream of a failure, every other stale rule with `-k`, and only stale rules without it, failing at least once. A failing build is followed by a second one, in place of the no-op. The fresh build runs with `-k` on one job, since with more every stale compile starts before the first failure and a `-k` that stops there would go unseen, and must write every output no failure blocks, and each rule an incremental build executed or found current must leave the bytes the fresh build wrote. A record changes only for a row that printed `ran`, and goes for one that printed `failed`, so the build after a fix executes exactly the rows whose facts differ from their record. `fix_files` restores the text each file held before it broke, which makes current again a rule that a stopped build never reached.
- Which stale rules a build without `-k` executed before stopping depends on the schedule, so no draw may depend on the outputs on disk, or Hypothesis reports `FlakyStrategyDefinition`. An edit to an output draws from every declared output and does nothing where the drawn one is absent. Orphans are likewise counted from every fresh build, failing ones included.
- After `let_files_settle`, every invocation starts on a clock 10 s ahead, past the racy margin, so the hash cache trusts each entry whose stamp a stat matches. Each build then ends by waiting for the file system's tick, so no later edit shares a stamp with a hash, and with `keeps_mtimes` only the ctime shows an edit.

## What it cannot see

- A new file outside the root that a search finds first is undetectable by design, since Facere lists only the root. The family therefore searches `../sdk` last.
- An interrupted recipe, a graceful stop, an input edited while a recipe runs, tasks, directory outputs, and links inside a directory input are outside the family. Without a task each invocation is one batch, so a failure's stop before the targets after it goes unchecked.
- A build without `-k` runs on the default job count, so which stale rules it executed before stopping is up to the schedule, and the machine checks only that each was stale. A failing recipe raises before writing, so a half-written output is never left in place.
- An edit that shares a stamp with a hash, which only the racy margin guards against, never happens once files settle, and before that every entry is racy and reread. A coarse or networked file system and clock skew are outside the family too.
