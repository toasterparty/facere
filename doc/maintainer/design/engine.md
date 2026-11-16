# The dependency engine

`src/facere/_engine.py` decides which rules are stale, why, and in what order they run. It imports nothing from Facere and touches no file, clock, or thread, so every decision can be tested with literal digests in microseconds, and a second implementation, such as one in C for a host that is not Facere, can be checked against the same tests.

## Model

A **key** is anything with a digest, and a **step** is work that reads keys and writes keys. Facere's keys are paths and its steps are rules, but the engine knows neither. A **trace** is the record of a step's last success: the step's own digest, and the digest of each key it read and wrote. A step is stale when its trace is missing or disagrees with the digests as they are now.

In the terms of "Build Systems a la Carte" (Mokhov, Mitchell, Peyton Jones), this is a topological scheduler over the steps the targets reach, with a verifying-trace rebuilder. Steps downstream compare the digests of what a step wrote, not whether it ran, which is what stops a rebuild at a step that ran again to the same bytes.

The engine guarantees, for every graph:

- a step runs exactly when it has no trace, or its own digest, a key it reads, or a key it wrote differs from its trace
- a build ends with every key the targets reach as a build from nothing would leave it
- a second build runs nothing
- no step runs twice in a session, or before every step upstream of it has settled

`test/engine/test_properties.py` checks the first three against a brute-force model for every graph of up to three steps and every single edit to one, and the last, with pool limits, under simulated workers polling in random order. `test/oracle/` checks the second through the whole of Facere.

## Interface

The host polls the engine and answers each event. The engine never calls the host, so a Python exception or an interrupt never crosses it, and it works under any threading model.

| Event | Meaning | Answer |
|---|---|---|
| `NeedDigests(step, keys)` | observe each key as it is now | `give_digests`, with `None` for a key with nothing there |
| `Run(step, verdict)` | the step is stale, for the reason the verdict holds | forget the step's saved trace, run it, then `finish(step, status, found)` |
| `Built(step, trace)` | the step ran and wrote every output | save the trace, which is `None` where it finished `UNSETTLED` |
| `Failed(step, missing, key)` | the engine failed the step: an input, an output, or an input it found has no digest | report it |
| `Pause.IDLE`, `Pause.DONE` | nothing to hand out, for now or for good | wait for another worker's answer, or stop |

A finish is `OK`, `FAILED`, or `UNSETTLED`, which succeeded but leaves no trace, as Facere reports for a rule whose input [changed during its recipe](./fingerprints.md#changes-during-a-recipe). `found` holds the inputs the step discovered while running, which join its trace.

`decide(step, trace, digests)` is the whole staleness decision as a pure function, returning a verdict or the keys it still needs. It reads a step's inputs first, and its found inputs and outputs only once the trace matches those, so a step already known stale costs no stat of its outputs. Keys are asked for a step at a time, not one by one, since each event costs a host with several workers a turn at its mutex. The reasons, in the order checked, are `INPUT_MISSING`, `ALWAYS`, `NO_TRACE`, `STEP_CHANGED`, `INPUT_CHANGED` and `OUTPUT_CHANGED` with the key, and `CURRENT`. `--check` and the `-v` reasons are to print these verdicts, the ones a build acts on, so neither can disagree with it.

An `Engine` is one session. It observes each key once and keeps the digest, so a session is correct for the keys as they stood when it first looked, and it asks again only for a step's outputs once that step ran. A later `request` in the same session checks only what no earlier one settled. Facere starts a new session after each task, since a task may change any file.

## Threads

The engine holds no lock. One mutex of the host's is all a parallel build needs, and every worker runs the same loop: take the mutex, poll, give it back while working, take it to answer, and wake the workers that got `IDLE`. That is correct because:

- every call returns at once and does no I/O, so holding the mutex across it is safe
- an event is handed out once, to the caller that polled it, and a step again only in a later session
- a `Run` arrives only once every step upstream is settled, and takes its pool's room as it is handed out
- `IDLE` means other workers hold what everything left waits on, so waking the idle after each answer is the whole wake-up rule

Among the steps that are ready, the one declared first is handed out first, so one worker gives a reproducible order, and the order between recipes comes from the graph alone, never from the order of the targets. With `keep_going`, a failure skips only the steps downstream of it. Without it, or after `stop`, no further step is checked or run, while the steps running finish and are traced. Facere uses one worker, no pool, and neither option until [scheduling](./execution.md#scheduling) is built on them.

## Found inputs

A key that a trace found orders its step after the step that now outputs that key, as a declared input does, even where the step declares no such input and the targets do not otherwise reach that step. So a report recorded while a file was a source never lets its rule be checked before the rule that now generates the file.

Such an edge exists only in the record, so it can contradict the graph: the step that now outputs the key may itself be downstream of the recording step, as when a rule stops reading a header and the header's rule starts to read that rule's output. A cycle error there would fail a correct project until its state was deleted, and ignoring the edge would check the recording step against a file about to be rewritten. The engine refuses the trace instead, so the step runs again, which is the only way to learn what it reads now. If it still reads the key, Facere fails it for [reporting an output it is not ordered after](./fingerprints.md#added-inputs).

## The file adapter

Facere's side of the engine is `_build.py`, with the graph built in `_collect.py`:

- A key is a path as `normalize` returns it, spelled as declared, since two sources differing only in case are two files on Linux. Outputs are also indexed by their case-folded key, which answers what the graph cannot: which output holds a given path.
- Containment becomes plain edges. An input inside a directory output, or a directory input holding outputs, gets an order-only key for each such output, so the engine orders the rule after their rules while only the input's own digest decides staleness. For a found input, `load_trace` takes the keys to follow in place of the keys found, so one inside a directory output follows that directory.
- An output is hashed afresh whenever the engine asks, and any other path as the session first saw it. The host keeps what it told the engine of each path, with its stamp, and compares against that after a recipe, so a rule is recorded only where nothing it read moved since the engine decided on it.
- The damage checks, the snapshot, shadowing, the `moved` table, tasks, and every message stay in the host. Shadowing reaches the engine as `forget_trace`.

## Scenarios

`test/engine/scenarios/` holds one transcript per behavior: a graph, its saved traces, and the host calls with the events `poll` must return between them. The files hold only names, keys, and digests, in a line format `test/engine/scenario.py` documents, so a second implementation replays them unchanged. A change to the engine's behavior changes a scenario in the same commit, and a new behavior adds one.

## Beyond Facere

A host that loads assets while running needs what Facere never exercises, so none of it is in the Python engine: a step that learns its inputs only by running and must run again once they exist, which is also the `dyndep` mechanism the [roadmap](../roadmap.md) defers, invalidating one key in a live session, and releasing the keys a new target set no longer reaches. Each fits the polled interface as a finish status, a call, and an event.
