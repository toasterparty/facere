# Names and scopes

## Declaring names

- **Scopes.** `with fac.scope(name, out=name, default=False):` opens a scope: rules, tasks, groups, and scopes defined inside it answer to `name.` followed by their own name. `out` names the subdirectory of the enclosing scope's output directory where `fac.out()` places paths for everything inside the scope, helpers included. It defaults to the scope's name, so a configuration takes one call and a helper used under several names never collides with itself. `out=None` keeps the enclosing output directory, for a scope that only names, such as a `run` scope gathering every program's run tasks. Scopes nest, and a rule or task remembers the scope it was defined in, so `fac.out()` in its recipe agrees. Paths outside the output directory are unaffected, so a rule outputting one, such as a fetched `third_party/` tree, belongs outside any repeated scope, where it would make two rules output one path. Several configurations of one project, such as debug and release builds, are one loop over scopes in one graph, as [C support](./extensions/c.md) shows.
- **Names.** Dropping one trailing underscore lets `def format_()` answer to `format` without shadowing the built-in. Names are dotted, as in Python: each `fac.py` directory and each `fac.scope` is a scope, so `lib.test` is `test` in `lib/fac.py`. A directory's scope name is its name as written, so `my-lib.test` works on the command line. Rules in one scope share a name only when they run the same function, and each rule stays addressable by its output paths. No two tasks share a dotted name, having no output to address them by, so a task with several programs to run, such as every test binary, runs them itself, through a thread pool when they should run in parallel.
- **Defaults.** A scope's name alone builds its `default=True` rules, tasks, groups, and scopes, else every rule in it, so `fac lib` executes `lib.clean` only if it is a default, and a task otherwise executes only when named.
- **Groups.** `fac.group(name, *targets, default=False)` names a group in the scope open where it is called, so inside `with fac.scope("test", out=None)` it answers to `test.<name>`, and `fac.group("all", "*.debug", "*.release", default=True)` makes a bare `fac` build every configuration. Each target is written as on the command line and resolved once collection ends, relative to the `fac.py`'s own scope whatever scope is open, as paths resolve from the `fac.py`'s directory, so a group may name what any `fac.py` defines, other groups included.

## Targets

An argument before `--` whose text before its first `=` is a Python identifier fails, naming `--`, so `fac flash PORT=/dev/ttyUSB2` points a Make user at task arguments rather than at a missing path. A file whose name holds `=` is written `./a=b`. An argument containing `::` names a rule or task by its `fac.py`'s path and its name within that file, as pytest's node ids do, so `my.lib/fac.py::server.release.run` reaches a task in a directory whose name holds a dot, which no dotted name can spell. An argument ending in `]` names a virtual output: the text before its last `[` resolves as below, to a `FileStore`'s path or to a rule's name, and the text inside matches a virtual output's key as messages show it, building only the rule that writes that virtual output. Otherwise, an argument containing a path separator is a path relative to the root, building the rule that outputs it or, for a directory, every rule with an output inside it. Any other argument is a dotted name, resolved from the root's `fac.py`.

A `*` matches exactly one part of a name, wherever it stands, so `fac 'tests.*.run'` runs every configuration's tests, and a subdirectory's release scopes are `lib.*.release`. zsh rejects an unquoted `*` or `[` that matches no file, so the docs and Facere's own messages quote every pattern. A name that matches nothing fails, suggesting the path when one exists, so `fac build` suggests `build/`, and a file in the working directory is written `./a.o`.

| Argument | Resolves to |
|---|---|
| `test` | `test` in the root's `fac.py` |
| `lib.test` | `test` in `lib/fac.py` |
| `server` | the `server` scope's defaults, else every rule in it |
| `server.release` | the `release` scope inside the `server` scope |
| `server.*` | everything named in the `server` scope |
| `*.release` | every `release` one level below the root's scope |
| `lib/fac.py::server.release.run` | `run` in the `server.release` scope of `lib/fac.py` |
| `build/src/main.o`, `./main.o` | the rule that outputs that file |
| `build/server/release/` | every rule with an output inside `build/server/release/` |
| `build/rows.txt`, a `FileStore`'s path | every rule writing a virtual output of it |
| `build/rows.txt[7]` | the rule writing the `FileStore` virtual output keyed `7` |
| `page[about]` | the rule named `page` writing the virtual output keyed `'about'` |
