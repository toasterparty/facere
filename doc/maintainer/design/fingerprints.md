# Fingerprints and checks

Timestamps cannot decide what is stale. `git checkout` stamps every file it touches with the current time, archive extraction and `cp -p` preserve old times, FAT stores them at 2 s granularity, and a changed compiler flag touches no file at all. Facere compares content fingerprints instead.

| Node | Declared by | Up to date when |
|---|---|---|
| Source | an input no rule outputs, a [store](./stores.md)'s virtual output included | always, and must exist |
| Rule | `@fac.rule` | its recorded fingerprint matches, its [added inputs](#added-inputs) are unchanged, and its outputs are intact |
| Rule that always executes | `@fac.rule(always=True)` | never, though rules downstream re-execute only when its outputs' content changed |
| Task | `@fac.task` | never: it executes whenever requested |

## What a fingerprint hashes

- its function's syntax tree without positions or docstring, and that of every function and class under the root its code names through a global, a closure variable, or a shared module's attribute, along with the function a decorator wraps, found through `__wrapped__`, and the classes under the root a class inherits from, so reformatting or editing a comment or docstring re-executes nothing
- for code under the root it reaches other than by name, the syntax tree of the whole module defining that code: the module of each value's class, such as a dataclass whose methods the recipe calls, and of each function or class a value holds, such as a dict of handlers. An edit anywhere in that module re-executes every rule holding such a value, which re-executes more than needed but never leaves one stale
- its values, the arguments its parameters other than inputs and outputs receive, and the module constants its code reads, a shared module's included, along with those of every function it reaches and the default arguments each such function binds at definition
- the variables `fac.env` sets for every command
- the Python minor version, as in `3.13`: a minor release may change what the same code does and how its syntax trees dump, and a patch release does neither
- the path and content of each input, where a file's content is its bytes and, on POSIX, its executable bit, and a link inside a directory input hashes as its target's content
- the path of each order-only input, never its content, since a recipe may derive flags from the list, so changing which headers a compile orders after re-executes it
- the path of each output by parameter, so swapping two outputs between parameters re-executes the rule
- the store, key, and value digest of each virtual input, and the code of the store of each virtual output

Hashing other rules' outputs, virtual outputs included, rather than whether those rules executed, means a rule that re-executes to identical bytes leaves everything downstream untouched.

A value hashes by its type: `None`, `bool`, `int`, `float`, `str`, and `bytes` by value, tuples and lists by element, dicts by item in insertion order, sets and frozensets sorted, since their iteration order varies with `PYTHONHASHSEED`, dataclasses and named tuples by class name and fields, a store of any class by qualified class name and attributes, enums by class and member name, `range`, `datetime.date`, `datetime.time`, `datetime.datetime`, `decimal.Decimal`, and `fractions.Fraction` by value, and functions and classes by qualified name, together with their module's syntax tree when it lies under the root. Any other type fails collection, and the error names the type and the fix where one is known, so a `pathlib.Path` fails asking for `path.as_posix()`.

## Added inputs

`fac.add_inputs(paths)`, called in a recipe after its tool has run, reports the files the recipe read, usually by parsing a depfile. They are recorded after each success and checked on the next invocation, as in ninja. Facere normalizes each path to root-relative with `/`, against the root's resolved path and keeping case, so a depfile's `src/a/../b.h` and MSVC's absolute paths need no cleanup. It keeps every report wherever it lies, system headers and a sibling checkout's included, so a project moving from make or ninja loses no rebuild, and the hash cache makes each file one stat per invocation however many rules report it. A report inside the output directory that no rule outputs is scratch, such as a header the recipe itself rewrote, so Facere keeps only its name, for shadowing below, since tracking it would execute the rule again after every execution. An SDK a project fetches belongs in a rule's output, pinned by a version in that rule's values, rather than outside the root. An order-only input the report lists joins the rule's record, and one it omits only orders the build, so a generated header declared on every compile of a library re-executes just the compiles that include it. A declared `fac.Input` always counts, so a recipe that reads one in Python never loses it. An added input that no longer exists makes the rule stale rather than failing as a missing source, while one missing when the recipe reports it fails the rule, since a rule that recorded it would never settle. Only a rule's recipe may report, since a task records nothing. The core parses no format of its own.

Facere also keeps the file name of every added input, those outside the root included, and a new file under the root with one of those names makes the rule stale, since a tool searching a path may find it first, as a new root `stdlib.h` would shadow the header a compile found. New files show up as the difference between the tree's listing and the saved one. An invocation saves the listing when it finds a difference and again as it ends, failed or not, if it executed anything, so a file a recipe wrote under the root never counts as new by the listing. Outputs are matched by name instead, wherever they lie: a declared output new at collection, and a file new in a directory output whenever its tree is hashed, since a generated header shadows as well as a hand-written one. An invocation that finds no difference and executes nothing pays one walk of the tree, and a false match costs one re-execute. A match forgets the rule's record at once, so it stays stale though this invocation's targets do not reach it. A project whose recipes report nothing never walks the tree.

When a rule reports an input that another rule outputs, and none of its own inputs is an output of that rule or a directory holding one, the invocation fails naming both: the first may have raced on it, and without the input the next one might too. A file inside a directory output counts as that rule's output, for a declared input as for a report, so an input naming one orders its rule after the directory's. A recorded added input that a rule now outputs orders the recording rule after that rule as soon as it is checked, as ninja's deps log does, so a report recorded while the file was a source never lets its rule be checked first.

## The hash cache

Each hash is cached against the file's size, mtime, ctime, and inode, as git's index does, so an untouched file costs one stat. A store's virtual output digests are cached against its stamp, so a `FileStore` of any size costs one stat too. ctime cannot be set by tools, which catches the same-size `cp -p` that mtime alone misses, and the writers of fixed mtimes, such as npm stamping every package file 1985-10-26 and reproducible archives. Windows keeps a change time too, read through a handle on each file, so the cache misses there what it misses on Linux, at a slower no-op than a directory listing alone would give.

An entry pairs its hash with a stat taken before the read, since a stat taken after pairs new timestamps with old bytes. It is racy, and rehashed rather than trusted, while its file last changed less than 2 s before the start of the invocation that recorded it, measured against that start rather than when the state was saved, minutes later. Timestamp granularity cannot be known, from ext4's timer tick to FAT's 2 s, so the margin is fixed. Every output is born racy, so an invocation with nothing stale rewrites its racy entries, letting them settle. A directory output is hashed by walking its tree through the same cache.

## Outputs

Declared outputs are what let Facere catch two rules writing one file and notice a recipe that succeeded without producing its file. Outputs are hashed after each success and re-verified on the next invocation, so an output edited, truncated, or deleted by hand gets rebuilt. What a rule declares is what Facere tracks: a rule unpacking a vendor toolchain can declare only its driver, and let the recipe's own check, such as an assertion on the driver's `--version` output, vouch for the rest.

A rule's fingerprint is taken before its recipe starts, and that fingerprint, not one taken afterward, is what a success records. An added input in the rule's record keeps the hash taken as the rule was checked. An invocation is correct for the files as they stood when it started, and an edit made while it executes is caught by the next one: before recording a rule, Facere stats each declared input and recorded added input again, and leaves the rule unrecorded where a stat moved since its fingerprint, even if the content changed back, as after a `git switch` and back during a long recipe. A file first reported has no earlier hash, so a change to it after the recipe started, by its timestamps, leaves the rule unrecorded too. That costs stats only for rules that executed. A tool that rewrites its own input on every execution never settles, which `--check` reports rather than every invocation.

## Undeclared paths

A recipe using an undeclared file under the root fails, naming the parameter to add, so editing a generator script re-executes what it generates, and a fetched or built tool run without its input fails instead of going stale.

`fac.run` checks every argument, the program included, and each part of a flag split at `=` and `,`, as in `--output-file=build/x.c` and `-Wl,-Map=build/fw.map`, against the files under the root outside the output directory and every path a rule outputs, wherever it lies, a file inside a directory output included. A Python audit hook, as PEP 578 defines, sees each file the recipe's own thread opens for reading and checks it the same way. Facere installs the hook once per process, on the first invocation, since PEP 578 hooks cannot be removed, and checks an event only when raised on the thread of a recipe the active invocation is executing, so repeated `fac.main()` calls, a test suite's included, pay for one hook.

Exempt are:

- paths a parameter annotated `str` holds
- shared modules a recipe opens, as printing a traceback does. A command given one fails, since its code joins a fingerprint only where the recipe reaches it by name
- files that no rule outputs, outside the root, in the output directory, such as a depfile, or in a hidden directory, where `sys.executable` lies in a project's `.venv`
- files the recipe reported through `fac.add_inputs` before using them, which covers a recipe that discovers what to read in Python
- files the recipe itself wrote from Python earlier in its execution, such as an archive's extracted tree it verifies

Writes stay with the damage checks below, so a rule declaring only part of what it unpacks still executes. A task records nothing, so its commands and opens go unchecked, and a cleanup task may name any output without building it first.

## Undeclared writes

Facere cannot see what a recipe writes or deletes, so it checks for the damage instead. Before a rule executes, an input built earlier in the invocation whose hash no longer matches what its rule recorded, or that is gone, fails the rule without executing it, naming the input and its rule. At the end of an invocation, Facere re-checks every output it built, one stat each, and fails naming any whose content changed after its rule finished. One that vanished passes, since the next invocation rebuilds it, so `fac app clean` succeeds. Damage done before an output's rule executes, as when a fetch replaces a directory before the compile that writes into it, needs no check, since that rule rebuilds its output. An invocation with nothing to do builds nothing and re-checks nothing.

## Open risks

The user docs list these in [hidden inputs](../../user/7-best-practices.md#hidden-inputs), which changes with this list.

- **Values read at run time.** A recipe that reads an environment variable, or anything else besides files, while it executes leaves it out of the fingerprint.
- **Inherited variables** stay out of the fingerprint, so one that changes an output, such as `CPATH`, `LC_ALL` for `sort`, or `SOURCE_DATE_EPOCH`, goes unnoticed until the project writes it through `env=` or `fac.env`.
- **The standard library and Facere's own modules**, which recipes call, are hashed by name only, so upgrading Facere or a Python patch release re-executes nothing, unless the Facere release changes what a fingerprint holds.
- **What a store cannot see.** A store's `read` that skips part of its file, or a `stamp` that misses a change, leaves that part or that change untracked.
- **Unresolved code.** Code a recipe reaches through a computed name, as with `getattr(module, name)` or `importlib.import_module`, stays out of the fingerprint.
- **Programs** stay out of the fingerprint unless the project declares them, as an input or as a version in a value. Facere does not hash what a command launches on its own: that would see only the launcher, not `as` and `ld` behind `gcc` or zig behind `uvx`, and would rebuild everything when the launcher alone is upgraded.
- **Clock skew.** A racy entry is measured against the local clock, and a file's timestamps come from its file server, so a server behind by more than the margin makes a racy entry read as settled.
- **Reads that raise no `open` event**, such as `os.listdir`, `os.scandir`, `os.path.exists`, `os.rename`, and `sqlite3.connect`, escape the undeclared-path check.
- **Files looked for and absent**, as with `__has_include`, leave no name to shadow, so creating one makes nothing stale.
- **Orphans.** A file Facere stopped tracking stays in place and is a source to any rule that inputs it, so a consumer of a renamed output still builds, and a recipe that stops writing an output leaves the last execution's file, which Facere records.
- **Paths joined to a flag** without `=` or `,`, such as `-Ibuild/gen`, escape the undeclared-path check, as do files opened from threads a recipe starts itself.
- **Files a command wrote** under the root, outside the output directory, are not known as the recipe's own, so using one later in that recipe fails unless the recipe reports it first.
- **Shadowing the listing misses.** A new file in a hidden directory, the output directory, or behind a linked directory is never listed, and one a command writes under the root while an invocation executes counts as that invocation's own, so either can shadow a file a rule read without making the rule stale. An output outside the root, such as a header installed into `../sysroot/include`, is matched only by name.
- **Incomplete added inputs.** A recipe that omits a rule-built file its tool reached indirectly, such as a header found through an include path, leaves the rule stale when that file changes.
- **Undeclared inputs**, files a command's program reads without its arguments naming them, such as a config file a tool finds on its own, go unnoticed, as in every tool short of tracing tools like tup and the ptrace-based fac, or sandboxed ones like Bazel.
- **Dependencies known only after a scan**, such as the imports of C++20 modules, have no mechanism like ninja's `dyndep`, and neither does a generator that chooses its own output names, such as protoc emitting a file per service.
