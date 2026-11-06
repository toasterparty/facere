# Fingerprints and checks

Timestamps cannot decide what is stale. `git checkout` stamps every file it touches with the current time, archive extraction and `cp -p` preserve old times, FAT stores them at 2 s granularity, and a changed compiler flag touches no file at all. Facere compares content fingerprints instead.

| Node | Declared by | Up to date when |
|---|---|---|
| Source | an input no rule outputs, a [store](./stores.md)'s virtual output included | always, and must exist |
| Rule | `@fac.rule` | its recorded fingerprint matches and its outputs are intact |
| Rule that always executes | `@fac.rule(always=True)` | never, though rules downstream re-execute only when its outputs' content changed |
| Task | `@fac.task` | never: it executes whenever requested |

## What a fingerprint hashes

- its function's syntax tree without positions or docstring, and that of every function and class under the root its code names through a global, a closure variable, or a shared module's attribute, so reformatting or editing a comment or docstring re-executes nothing
- for code under the root it reaches other than by name, the syntax tree of the whole module defining that code: the module of each value's class, such as a dataclass whose methods the recipe calls, and of each function or class a value holds, such as a dict of handlers. An edit anywhere in that module re-executes every rule holding such a value, which re-executes more than needed but never leaves one stale
- its values, the arguments its parameters other than inputs and outputs receive, and the module constants its code reads, a shared module's included, along with those of every function it reaches
- the variables `fac.env` sets for every command
- the path and content of each input
- the store, key, and value digest of each virtual input, and the code of the store of each virtual output
- the path and content of each input the recipe added at its last execution, order-only inputs it reported reading included

Hashing other rules' outputs, virtual outputs included, rather than whether those rules executed, means a rule that re-executes to identical bytes leaves everything downstream untouched.

A value hashes by its type: `None`, `bool`, `int`, `float`, `str`, and `bytes` by value, tuples and lists by element, dicts by item in insertion order, sets and frozensets sorted, since their iteration order varies with `PYTHONHASHSEED`, dataclasses and named tuples by class name and fields, a store of any class by qualified class name and attributes, enums by class and member name, `range`, `datetime.date`, `datetime.time`, `datetime.datetime`, `decimal.Decimal`, and `fractions.Fraction` by value, and functions and classes by qualified name, together with their module's syntax tree when it lies under the root. Any other type fails collection, and the error names the type and the fix where one is known, so a `pathlib.Path` fails asking for `path.as_posix()`.

## Added inputs

`fac.add_inputs(paths)`, called in a recipe after its tool has run, reports the files the recipe read, usually by parsing a depfile. They are recorded after each success and checked on the next invocation, as in ninja. Facere normalizes each path to root-relative with `/` and drops any outside the root, such as system headers, so a depfile's `src/a/../b.h` and MSVC's absolute paths need no cleanup. An order-only input the report lists joins the fingerprint, and one it omits only orders the build, so a generated header declared on every compile of a library re-executes just the compiles that include it. A declared `fac.Input` always counts, so a recipe that reads one in Python never loses it. An added input that no longer exists makes the rule stale rather than failing as a missing source. The core parses no format of its own.

Facere also keeps the file name of every added input, those outside the root included, and a new file under the root with one of those names makes the rule stale, since a tool searching a path may find it first, as a new root `stdlib.h` would shadow the header a compile found. New files show up as the difference between the tree's listing and the previous invocation's, so an invocation that finds none pays nothing, and a false match costs one re-execute.

When an added input is output by a rule none of whose outputs the reporting rule inputs, the invocation fails naming both: the first may have raced on it, and without the input the next one might too. A file inside a directory output counts as that rule's output.

## The hash cache

Each hash is cached against the file's size, mtime, ctime, and inode, as git's index does, so an untouched file costs one stat. A store's virtual output digests are cached against its stamp, so a `FileStore` of any size costs one stat too. On Windows, where a stat per file is slow, the size and mtime come from each directory's listing instead, which `os.scandir` returns without one. ctime cannot be set by tools, which on Linux catches the same-size `cp -p` that mtime alone misses, and a file modified too close to the last invocation for its timestamps to be trusted is rehashed anyway, as git does for racy entries. A directory output is hashed by walking its tree through the same cache.

## Outputs

Declared outputs are what let Facere catch two rules writing one file and notice a recipe that succeeded without producing its file. Outputs are hashed after each success and re-verified on the next invocation, so an output edited, truncated, or deleted by hand gets rebuilt. What a rule declares is what Facere tracks: a rule unpacking a vendor toolchain can declare only its driver, and let the recipe's own check, such as an assertion on the driver's `--version` output, vouch for the rest.

A rule's fingerprint is taken before its recipe starts, and that fingerprint, not one taken afterward, is what a success records. An input that changed during the recipe then mismatches on the next invocation and rebuilds the rule, and one that did not change costs nothing. Inputs a recipe adds through `fac.add_inputs` have no earlier hash, so they join the record as hashed after the recipe.

## Undeclared paths

A recipe using an undeclared file under the root fails, naming the parameter to add, so editing a generator script re-executes what it generates, and a fetched or built tool run without its input fails instead of going stale.

`fac.run` checks every argument, the program included, and each part of a flag split at `=` and `,`, as in `--output-file=build/x.c` and `-Wl,-Map=build/fw.map`, against the files under the root outside the output directory and every path a rule outputs, wherever it lies, a file inside a directory output included. A Python audit hook, as PEP 578 defines, sees each file the recipe's own thread opens for reading and checks it the same way. Facere installs the hook once per process, on the first invocation, since PEP 578 hooks cannot be removed, and checks an event only when raised on the thread of a recipe the active invocation is executing, so repeated `fac.main()` calls, a test suite's included, pay for one hook.

Exempt are paths a parameter annotated `str` holds, shared modules, which Facere hashes, files outside the root that no rule outputs, scratch files in the output directory that no rule outputs, such as a depfile, and files the recipe itself wrote earlier in its execution, such as an archive's extracted tree it verifies. Writes stay with the damage checks below, so a rule declaring only part of what it unpacks still executes. A task records nothing, so its commands and opens go unchecked, and a cleanup task may name any output without building it first.

## Undeclared writes

Facere cannot see what a recipe writes or deletes, so it checks for the damage instead. Before a rule executes, an input built earlier in the invocation whose hash no longer matches what its rule recorded, or that is gone, fails the rule without executing it, naming the input and its rule. At the end of an invocation, Facere re-checks every output it built, one stat each, and fails naming any whose content changed after its rule finished. One that vanished passes, since the next invocation rebuilds it, so `fac app clean` succeeds. Damage done before an output's rule executes, as when a fetch replaces a directory before the compile that writes into it, needs no check, since that rule rebuilds its output. An invocation with nothing to do builds nothing and re-checks nothing.

## Open risks

The user docs list these in [hidden inputs](../../user/7-best-practices.md#hidden-inputs), which changes with this list.

- **Values read at run time.** A recipe that reads an environment variable, or anything else besides files, while it executes leaves it out of the fingerprint.
- **Inherited variables** stay out of the fingerprint, so one that changes an output, such as `CPATH`, `LC_ALL` for `sort`, or `SOURCE_DATE_EPOCH`, goes unnoticed until the project writes it through `env=` or `fac.env`.
- **The standard library and Facere's own modules**, which recipes call, are hashed by name only, so upgrading Python or Facere re-executes nothing.
- **What a store cannot see.** A store's `read` that skips part of its file, or a `stamp` that misses a change, leaves that part or that change untracked.
- **Unresolved code.** Code a recipe reaches through a computed name, as with `getattr(module, name)` or `importlib.import_module`, stays out of the fingerprint.
- **Programs** stay out of the fingerprint unless the project declares them, as an input or as a version in a value. Facere does not hash what a command launches on its own: that would see only the launcher, not `as` and `ld` behind `gcc` or zig behind `uvx`, and would rebuild everything when the launcher alone is upgraded.
- **Windows has no change time** in `os.stat`, so the hash cache misses a same-size file replaced with its old mtime, the `cp -p` case ctime catches on Linux.
- **Paths joined to a flag** without `=` or `,`, such as `-Ibuild/gen`, escape the undeclared-path check, as do files opened from threads a recipe starts itself.
- **Shadowing from hidden directories.** A new file in a hidden directory is never listed, so it can shadow a file a rule read without making the rule stale.
- **Incomplete added inputs.** A recipe that omits a rule-built file its tool reached indirectly, such as a header found through an include path, leaves the rule stale when that file changes.
- **Undeclared inputs**, files a command's program reads without its arguments naming them, such as a config file a tool finds on its own, go unnoticed, as in every tool short of tracing tools like tup and the ptrace-based fac, or sandboxed ones like Bazel.
- **Dependencies known only after a scan**, such as the imports of C++20 modules, have no mechanism like ninja's `dyndep`, and neither does a generator that chooses its own output names, such as protoc emitting a file per service.
