# Stores and virtual outputs

A store is a user-defined value holding keyed virtual outputs, such as the rows of one file or the resources of an HTTP REST API. A rule writes and reads virtual outputs as it does files, and Facere tracks staleness per virtual output, so 1500 rows that go stale independently need not be 1500 files, and a page published to a CMS re-executes only when its own source changes.

The filesystem is the store Facere has built in, its virtual outputs are paths, and a project with one file per output uses `fac.Input` and `fac.Output`, paying nothing for stores. Internally a file output is a virtual output of that built-in store, so staleness, the hash cache, and the damage checks are one code path.

## Interface

```python
class Store(Protocol[K, V]):
    def stamp(self) -> object: ...
    def read(self, keys: Collection[K]) -> Mapping[K, V]: ...
    def update(self, changed: Mapping[K, V]) -> None: ...
```

- `stamp()` returns a cheap token that changes whenever any virtual output does, such as a collection's ETag or version counter, as a value Facere can hash, or `None` when the store has none.
- `read(keys)` returns the virtual outputs among `keys` that the store holds, and may return others, which Facere caches too. A key it omits is a missing virtual output.
- `update(changed)` writes the virtual outputs given, which Facere passes in rule definition order, and leaves every other virtual output as it was.

A store is an instance of an ordinary class, whose attributes say where it lies, such as a base URL. It needs no dataclass, freezing, or slots: Facere copies its attributes when collection ends and fails the invocation, naming the store, if a method changes one, since a store that moved mid-build would split its virtual outputs between two places. `fac.Store` exists only for type checking, so a store need not subclass it.

`fac.FileStore` is the one store class Facere ships, constructed as `FileStore(path)`, for a store kept in one file. A subclass implements `read()`, which returns every virtual output the file holds, and `write(outputs)`, which replaces the file with exactly the virtual outputs given. `FileStore` supplies `stamp`, the hash cache's stat of the file, and `update`, which reads the file, replaces the changed virtual outputs, and passes `write` every virtual output: first those the rules declare, in definition order, then the rest in the order `read` returned them.

`fac.Virtual(store, key)` names one virtual output, typed by the store's key and value types. It is a value, so it goes in `each=`, in keyword arguments to `fac.rule`, and in module constants. A parameter annotated `fac.VirtualOutput` or `list[fac.VirtualOutput]` declares virtual outputs the recipe writes, and `fac.VirtualInput` or `list[fac.VirtualInput]` virtual outputs it reads. They are annotations apart from `fac.Output` and `fac.Input`, since a virtual output that looked like a `str` would let `open(virtual output, "w")` overwrite a whole `FileStore`.

In a recipe, `fac.write(virtual_output, value)` sets one of the rule's virtual outputs, and a second call replaces the first value. `fac.read(virtual_input)` returns one of the rule's virtual inputs, from values written earlier in the invocation or from an earlier `read`, and a virtual output with no value in memory makes Facere call `read`. Both fail the recipe for a virtual output the rule does not declare, and a recipe that succeeds without writing every virtual output fails as one that leaves an output file missing does. Keys and values must be values Facere can hash, which collection checks for keys and `fac.write` for values.

## Identity

A store is identified by its class's qualified name and its attributes, so a store pointed at another URL is another store, and every rule writing to it re-executes. A `FileStore` is identified by its path instead. A rule's record is keyed by its output paths and virtual outputs.

## Staleness

Facere calls a store only when a rule the targets need declares one of its virtual outputs, so `fac` on file-only targets of a project that also publishes never reaches the network. It calls `stamp` at most once per invocation before the store's first flush, the first time a rule's staleness depends on the store, and a stamp equal to the one recorded with the cached digests, under the same code for the store, means those digests stand, since editing a source store's `read` changes what its virtual outputs hold without touching its file. A different stamp, or `None`, calls `read` with every key the needed rules declare, and Facere hashes each value with the value hasher, so a `read` may return a row's text, a tuple of columns, or a digest the server computed.

A virtual output that is missing, or whose digest differs from the record, makes its rule stale, so a page edited on the server is published again, as an output file edited by hand is rebuilt. A virtual input makes its rule stale when its digest differs, and a missing virtual output that no rule writes fails as a missing source does. A rule inputting a virtual output another rule writes executes after it, as for paths.

A `FileStore` whose file is missing has no virtual outputs, and `read` is not called. One whose `read` raises before Facere writes to it counts as holding no virtual outputs, so a file torn by an interrupted `write` costs rebuilds, never a stale record. Any other store whose `stamp` or `read` raises fails the invocation with status 1, naming the store, the method, and the exception: a server that cannot answer leaves staleness undecided, and Facere never reports success while an output may be stale.

A rule's fingerprint takes the store of each virtual output it writes as code, the class's methods and what they reach by name, as for a recipe. A change to how a store writes therefore re-executes every rule writing to it, where it would otherwise leave every virtual output in its old format with every record matching. A store does not hash its class's whole module, as other values do, so editing a task in the same `fac.py` re-executes none of them.

## Writing

`fac.write` only buffers the value, so 1500 recipes perform no I/O, and the store's own code decides how changes reach it, as one file write or one batched request. Facere flushes a store's buffered values:

- when the batch ends
- before a rule that inputs a `FileStore`'s path as a plain `fac.Input`, such as a tool reading the whole file
- on a failure or a graceful stop, keeping what finished and dropping the failed recipe's values. An interrupt flushes nothing, and the rules whose values it drops have no record, so they execute again

Once the state commits records every 100 ms, a flush precedes each commit. A flush calls `update`, then `stamp`, then `read`, and only then commits the records of the rules it flushed, so a crash between any two steps leaves those rules unrecorded, costing re-executes. A method that raises during a flush records none of them and fails the invocation with status 1. Taking the stamp before reading means a change landing between the two costs one more read, never a missed change.

The read-back is the round-trip check. Every virtual output written must hash as written, and every other virtual output the read returns must hash as recorded, so a `read` that disagrees with `write`, an `update` that disturbs virtual outputs it was not given, and a server that rewrites a value each fail the invocation, naming the virtual output, as the damage checks do for files.

Facere calls one store's methods one at a time, never concurrently, so a store needs no locking. A call may run on a worker thread, so a slow server delays only the rules that need its virtual outputs.

## Validation

Collection fails, naming the definitions involved, on two rules outputting one virtual output, a rule outputting a `FileStore`'s path as a plain `fac.Output`, two `FileStore` values on one path, and a virtual output whose store or key Facere cannot hash. A `FileStore` that no rule writes is a source store, such as a hand-edited table, and its virtual outputs are sources. A rule declaring a `FileStore`'s path as a plain `fac.Input` depends on every rule writing a virtual output of it, and `fac build/rows.txt` builds every such rule, as a directory target builds every rule inside it.

A `FileStore`'s path follows the rules of a `fac.Output` path, written relative to its `fac.py` and returned by `fac.out` in a form Facere recognizes, and its methods run with the root as working directory and `self.path` relative to the root, as a recipe's paths are. The undeclared-path check treats that path as an output, while the store's own methods, which Facere calls, are exempt.

## Reporting

A virtual output counts as an output in the closing line, so a no-op over 1500 rows reports 1500 outputs up to date. Messages show a virtual output as its `FileStore`'s path, or else as the name of the rule writing it, followed by its key in brackets, a string bare and any other key as its `repr`, as in `build/rows.txt[7]` and `page[about]`. A virtual output no rule writes shows its store's value instead. The same text, given as a target, builds the rule writing that virtual output, as [names](./names.md#targets) describes. `--paths outputs` prints a `FileStore`'s path once for all its virtual outputs and nothing for other stores, which have no file to name, and `--json` records list each virtual output with its store and key.

## Open risks

- **A stamp that misses a change**, such as a Last-Modified header with one-second granularity, keeps stale digests. A store whose server offers no reliable token returns `None` and pays a `read` per invocation.
- **What `read` leaves out** stays untracked, so a format whose `read` skips comment lines misses an edit to them.
- **The lock covers one output directory**, so two machines writing one remote store can collide. The round-trip check reports the collision afterwards, and only the store's own `update`, through `If-Match` or whatever the API offers, can prevent one.
- **Orphaned virtual outputs**, whose rules were removed, stay in the store, since Facere deletes nothing it no longer tracks, so the store protocol has no way to delete. Deleting the output directory removes every orphan of a `FileStore` inside it, as it does every orphaned file, while a remote store's orphans are the project's own to remove, such as through a task.
- **Memory.** `FileStore` holds every virtual output's value while it writes, so a store of millions of rows suits a format that changes rows in place, such as a SQLite table, written as a plain store.
- **Watch mode** observes a `FileStore`'s file as any file, and no other store, so a change on a server starts no cycle.
