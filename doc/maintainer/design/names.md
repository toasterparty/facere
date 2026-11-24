# Names and scopes

## Declaring names

- **Names.** Dropping one trailing underscore lets `def format_()` answer to `format` without shadowing the built-in. Names are dotted, as in Python: each `fac.py` directory and each `fac.scope` value is a scope, so `lib.test` is `test` in `lib/fac.py`. A part of a name holds only letters, digits, `_`, and `-`, and a name or target holding any other character outside the syntax below fails, so `**`, `?`, `@`, and `,` stay free for later syntax. A directory whose name holds another character, such as a dot, gives no name part, and its rules and tasks are reached through `::`. Rules in one scope share a name only when they run the same function, and each rule stays addressable by its output paths. No two tasks share a dotted name, having no output to address them by, so a task with several programs to run, such as every test binary, runs them itself, through a thread pool when they should run in parallel.
- **Scopes.** `fac.scope(name, out=name, default=False)` returns a scope, a value naming a group of rules and tasks and their place in the output directory. A parameter annotated `fac.Scope` defines its rule or task in that scope, answering to the scope's name followed by its own, under the directory scope of the `fac.py` that defines it, wherever the scope value was made. One holding `None` leaves its rule in that directory scope, so a helper passes an optional scope straight through. `scope.out(path, suffix=None)` places a path in the scope's output directory as `fac.out` does in the output directory, and `out` names that directory's place in the output directory. It defaults to the scope's name, so a configuration takes one call and a helper used under several names never collides with itself. `out=None` keeps the output directory, for a scope that only names, such as one per service gathering its `start` and `stop` tasks. `scope.scope(name, ...)` nests one scope in another, its output directory inside the outer one's. A path already in the scope's output directory keeps its place under `scope.out`, and one elsewhere in the output directory fails collection, naming both directories, so a rule inputting another scope's output writes that path directly. Paths outside the output directory are unaffected, so a rule outputting one, such as a fetched `third_party/` tree, belongs in no repeated scope, where it would make two rules output one path. Several configurations of one project, such as debug and release builds, are rows of one `each=`, each row carrying its scope, built by the plain `for` loops that build any rows.
- **Why a value.** A scope opened by `with` made a line's meaning depend on where it stood: `fac.out()` meant one directory at collection and another in a recipe, a shared module's rules joined whichever scope imported it first, and giving each of seven services three tasks took a `def` inside a `with` inside a `for`. As a value, a scope is declared like everything else, through an annotated parameter a row fills, and tasks take `each=` as rules do. The cost is that a helper that places outputs, such as an extension's, takes the scope as an argument, and `fac.out()` alone always means the output directory.

```python
SERVICE_TASKS = [{"scope": fac.scope(name, out=None), "service": name} for name in SERVICES]


@fac.task(each=SERVICE_TASKS)
def start(scope: fac.Scope, service):
    compose(service, "up", "-d")
```

- **Defaults.** A scope's name alone builds its `default=True` rules, tasks, groups, and scopes, else every rule in it, so `fac lib` executes `lib.clean` only if it is a default, and a task otherwise executes only when named.
- **Groups.** `fac.group(name, *targets, default=False)` names a group in the directory scope of the `fac.py` calling it, and `scope.group(...)` in a scope, so `fac.group("all", "*.debug", "*.release", default=True)` makes a bare `fac` build every configuration. Each target is written as on the command line and resolved once collection ends, relative to the `fac.py`'s own directory scope, so a group may name what any `fac.py` defines, other groups included.

## Targets

An argument before `--` whose text before its first `=` is a Python identifier fails, naming `--`, so `fac flash PORT=/dev/ttyUSB2` points a Make user at task arguments rather than at a missing path. A file whose name holds `=` is written `./a=b`. An argument containing `::` names a rule or task by its `fac.py`'s path and its name within that file, as pytest's node ids do, so `my.lib/fac.py::server.release.run` reaches a task in a directory whose name holds a dot, which no dotted name can spell. An argument ending in `]` names a virtual output: the text before its last `[` resolves as below, to a `FileStore`'s path or to a rule's name, and the text inside matches a virtual output's key as messages show it, building only the rule that writes that virtual output. One that matches no virtual output resolves as below, so a route directory such as `build/app/[slug]` stays a path. Otherwise, an argument containing a path separator is a path relative to the root, building the rule that outputs it or, for a directory, every rule with an output inside it. Any other argument is a dotted name, resolved from the root's `fac.py`.

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
