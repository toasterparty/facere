# Requirements

MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in capitals.

## General

- The user is the software developer who uses Facere to build their own project, and the reader of the user documentation in `doc/user/`.
- A concept MUST have one word across the Python interface, the command line, and the documentation. Facere SHOULD prefer plain English or a term already in its [terminology](../user/8-terminology.md) to coining a new one, and a term borrowed from another tool MUST keep that tool's meaning.

## Interface

### `fac.py`

- A project's build definition MUST be plain Python in `fac.py` files.
- A `fac.py` MUST mean only what its Python semantics say, with no string mini-language, magic variable, or name whose spelling changes what it does, except that one trailing underscore is dropped from a function's name when it becomes a rule's or task's name.
- Facere's own decisions MUST NOT depend on an environment variable, except through the programs `PATH` finds. Facere MAY read one only to find programs, as `PATH` and, on Windows, `PATHEXT` direct, to adapt its output to the terminal, as `NO_COLOR` asks, or to reach the network, as a proxy setting does.
- A rule's signature MUST declare the outputs its recipe writes and every input known before it executes, so a reader learns both without reading the recipe.
- Every other input MUST be reported by the recipe that read it, never guessed.
- A rule MUST be able to declare an input that orders the build but joins its fingerprint only once its recipe reports reading it, so a generated header is built first without rebuilding every compile that might include it.
- Rules MUST depend on one another only through their inputs and outputs, never by name.
- A rule MUST be able to write and read virtual outputs, keyed values held in a store, a value the project defines, such as the rows of one file or the resources of an HTTP REST API, so how finely Facere tracks outputs is independent of how they are stored. A project with one file per output MUST need no store.
- Facere MUST accept a source, so a project can add the rule that outputs it later without editing the rules that read it.
- Paths in a `fac.py` MUST be strings relative to its own directory, as a user standing there types them, with `/` separators on every OS.
- A `fac.py` MUST be able to change how the rules that read files under its own directory are built, with no edit outside that directory.
- Each `fac.py` MUST be loaded exactly once per invocation, so its rules and tasks are defined once. Code shared between `fac.py` files lives in ordinary Python modules.
- An import in the project's own code MUST NOT resolve outside the root while the root holds a module of that name, so another module never silently stands in for a shared module.
- A rule MUST be able to read, as values, the inputs, outputs, and values of rules defined elsewhere, so one rule can summarize others, as clang's `compile_commands.json` does.
- A command MUST run as it would from the user's shell, given the same arguments and environment, except where a requirement here says otherwise, so a tool behaves the same wrapped as unwrapped.
- Since commands run without a shell, Facere's interface for running a command MUST be able to redirect its standard streams to files.
- A rule's commands MUST run without a controlling terminal, and with no standard input but a file the recipe names, unless the rule requests a terminal, so a command that prompts fails at once instead of waiting.
- A task MUST execute alone, after every other recipe its target needs, and its commands MUST share Facere's standard streams, printing live and reading its stdin, since a user who names a task is waiting on it.

### Command line

- The root, the directory whose `fac.py` defines the project, MUST be the directory `fac` starts in, unless a flag names another.
- Targets are the names and output paths given on the command line. Names MUST reach everything a user commonly builds, configurations included, so output paths serve only scripts, agents, and debugging. Syntax alone MUST tell a name from a path.
- A project MUST be able to choose its names independently of where its outputs lie.
- Facere MUST be able to print, without executing any recipe, the paths of the inputs or the outputs of a target's rules, so a script that knows a target only by name finds its files without hardcoding where they lie.
- `fac` with no targets MUST build the defaults the root's `fac.py` declares, or, when it declares none, every rule and no task, so a first `fac.py` needs no declaration and a bare `fac` never starts a task unasked. A project with no rules MUST then succeed, doing nothing.
- Every rule and task MUST be addressable individually. A rule that outputs a virtual output MUST be addressable through that virtual output, in the form Facere's messages show it, so one page is published alone though its rule outputs no path.
- The user MUST be able to name a group of targets explicitly, such as `all` or `test`. Building a group builds every target in it, and a group MAY be one of the defaults. A group, and a scope given by its name, MUST build their targets as the same targets given in order on the command line would: a group's in the order it lists them, and a scope's defaults in the order they were defined.
- A pattern MUST be able to name several targets at once, such as every configuration of one program.
- Facere's own actions MUST be flags, so every name belongs to the user.
- Different flags MUST mean the same in any order, so two that contradict MUST be an error. A repeated flag MUST take its last value, so a wrapper's defaults can be overridden.
- A task MUST be able to receive arguments from the command line, in a form that cannot collide with Facere's own flags.

## Reporting

- By default, a successful invocation MUST leave no more than 3 lines of Facere's own output in the terminal. Output from the user's commands does not count. Lines that name a changed directory do not count.
- A successful invocation MUST end with one line giving its duration, the tasks and rules it ran, and the outputs it found up to date, leaving out what is zero. When nothing ran, the line MUST say there was no work to do, so a caller tells a build that was current from one that did nothing.
- An interrupted invocation MUST end with one line that says so and gives the same counts, under a line naming the rule or task it stopped.
- When Facere's own output is a terminal, it SHOULD show `[position/total] rule` on a status row pinned to the bottom, below the scrolling output of the commands, and erase the row when it ends for any reason, including a terminating signal. The row is transient, so it does not count toward the 3 lines.
- Facere MUST be able to report, without executing any recipe, which rules are stale and why, and which may execute once a stale rule upstream of them does, naming those stale rules. It MUST also be able to name why each rule that executes did.
- Facere MUST be able to emit its listing of rules and tasks, its staleness report, and its timings as JSON, the listing and the report sharing one record layout, so a script or agent reads structure instead of parsing prose.
- Facere MUST be able to print each command it runs, as one string, before running it.
- Facere MUST show what a rule's commands write, unaltered, and MUST let the user hide a successful command's output, for one command or for a whole invocation.
- When Facere's own output is a terminal, a rule's commands SHOULD see a terminal on their standard error, so a tool colours its diagnostics as it would unwrapped. What a recipe reads from a command's standard output MUST NOT depend on whether Facere had a terminal.

## Errors

- Facere's exit status MUST tell a failed recipe from an invocation that could not start the build, so a caller learns whether its own code or the build definition is wrong.
- An error detectable during collection, while Facere loads every `fac.py` and defines their rules, MUST be reported before any recipe executes.
- An error in a `fac.py` MUST name the `fac.py:line` of each definition involved.
- A failed recipe MUST lead with the failing command and its unaltered output, then name its rule, so a diagnostic from the user's tool is never buried under a location in the build definition.
- Facere's own errors MUST use the GNU `file:line:column: message` format, so an editor's problem matcher parses them as it does a compiler's.
- Anything in a `fac.py` Facere cannot interpret with certainty MUST be an error, including conflicting declarations, an ambiguous name, a parameter without a value, a value Facere cannot hash, and an undeclared path.
- A dependency cycle MUST fail collection, naming every rule in it.
- Every error MUST state what Facere attempted, on what, and what happened, and MAY name a remedy only where the [principles](./principles.md) allow one.
- Facere MUST be able to validate a project without executing any recipe, and the validation MUST pass on a fresh clone of a correct project.

## Correctness

- Staleness MUST be decided by content. Timestamps MAY key a cache of what files and directories hold, and a store's stamp a cache of what its virtual outputs hold, and both MUST serve no other purpose. A cache entry recorded less than one timestamp granularity after its file last changed MUST be rehashed rather than trusted.
- A rule's fingerprint, the hash that decides whether the rule is stale, MUST hold its recipe's code, every value it reads through its parameters or as a module constant, and its declared inputs. Facere MUST NOT infer what else can change an output, such as the programs its commands launch: the project declares what should count.
- The documentation MUST list every kind of input that stays out of fingerprints, so a user knows which risks they own.
- A file appearing in, disappearing from, or renamed within a rule's inputs, as when a glob's matches change, MUST make the rule stale, even when no content changed.
- A recipe MUST fail when Facere observes it using a file under the root that its rule does not declare, naming the declaration to add. A file in the output directory that no rule outputs is exempt, so a recipe can keep scratch files there.
- Facere MUST build the command-line targets in the order given. Consecutive targets that reach no task form a batch, which MUST be built together, in parallel, since the dependency graph alone orders rules. A target that reaches a task MUST start only once the targets before it finish, and finish before the targets after it start, so `fac clean app` deletes and then rebuilds. A rule's staleness MUST NOT be decided before its batch starts.
- Within a batch, an output changed after its recipe finished MUST fail the batch before any recipe consumes it, naming the output and its rule.
- A virtual output that a store does not read back as Facere wrote it MUST fail the invocation, naming the virtual output.
- A rule whose input changed while its recipe executed MUST NOT be recorded as up to date.
- Facere's decisions MUST NOT depend on what the output directory held before, beyond the outputs its state records. A recipe whose tool reads its own previous output is responsible for its own idempotency.

## Dependability

- Facere's decisions MUST be the same regardless of OS, environment, or job count, except through the programs `PATH` finds. Within a batch, the order between recipes MUST come from the dependency graph alone.
- Facere's core MUST NOT make a rule, path, or value differ between platforms or machines. Only Python a project runs may, a shipped extension's included.
- A command MUST inherit Facere's environment, and an inherited variable MUST NOT join any fingerprint, since Facere cannot tell which variables a command reads. A variable a project sets or unsets in Python, for one command or for all of its commands at once, MUST join the fingerprint of every rule whose commands receive it.
- A recipe MUST execute only when Facere needs its outputs or the user names its task, never during collection.
- Facere MUST NOT require a program that no requested target needs, so a developer building part of a project installs only that part's tools. A project MAY require more through its own code.
- Any exception a recipe raises MUST fail it, so an `assert` stops a bad result. Facere MUST warn when Python's assertions are disabled, since every recipe's checks then vanish.
- An output changed or deleted outside Facere MUST be rebuilt.
- A failed or interrupted recipe MUST leave nothing the next invocation accepts as up to date.
- Losing any of Facere's state, its record of past builds, between invocations MUST cost only rebuilds, never stale output.
- A rule MAY output any path or virtual output, and the output directory MAY lie anywhere but the root.
- Facere's state MUST lie in the output directory, so deleting the directory forgets all of it.
- Besides the terminal's interrupt, which MUST still stop everything at once, Facere MUST accept a request to stop gracefully: it starts no new recipe, lets running rules finish and records them, and stops a task's commands.
- A second invocation on the same output directory MUST wait for the first rather than fail or corrupt its state, unless waiting would deadlock, which MUST fail at once. While it waits, Facere MUST name the invocation it waits for, and the user MUST be able to bound the wait, so a caller with a deadline of its own can tell a wait from a hang.
- A task that keeps running, such as a server restarted on every save, MUST be able to let other invocations proceed while it runs.

## Performance

- An invocation with nothing stale MUST finish in under 300 ms on Linux on an Intel N100 under the oldest CPython Facere supports, for a synthetic project of 1000 C sources, 5000 headers, and one program, and for one of 10000 rules each writing one virtual output of a single file, so it can run on every save.
- With nothing stale, Facere MUST execute no recipe except those of rules declared to always execute, MUST write no file but its own state and lock, and MUST call no store but to take each needed store's stamp once.
- A rule that always executes MUST NOT make the rules downstream of it stale by executing. Only a change in its outputs' content does.
- Facere MUST NOT put an absolute path in a fingerprint, except where no relative path exists, as between Windows drives, so moving a checkout together with its output directory rebuilds only what reads an absolute path itself.
- Facere's core MUST NOT access the network. Only recipes and stores may, the recipes of shipped extensions included, and Facere MUST NOT call a store that no requested target needs.

## Extensions

- Extensions MUST use only Facere's public interface. They exist only to package rules that many users need.
- Extensions SHOULD follow the [best practices](../user/7-best-practices.md).
- An environment an extension creates for its own use, such as a virtual environment for an isolated tool or for one Python version, MUST lie in the output directory, so deleting the directory resets it. An extension MUST NOT create, relocate, or replace the environment of the project being built: that environment belongs to the user and their tools, and lies where those tools put it.

## Distribution

- Facere MUST ship as a pure-Python wheel with no dependency outside the standard library.
- Facere MUST support every CPython release whose status is bugfix or security, and officially supports no other.
- The user-facing documentation MUST ship as Markdown files in the wheel, written for agents as well as people: complete enough that an agent with only the installed package, and no network, writes a correct `fac.py` from it.
- `fac --help` MUST document every flag, target form, and exit status the release supports, and the user documentation MUST NOT repeat them.
- An editor MUST be able to complete and type-check a `fac.py`.
- Every release from 1.0 on MUST accept and build alike every `fac.py` an earlier release from 1.0 on accepted, except for behavior the maintainers judge to be a bug. Releases before 1.0 MAY break any interface.
- A project MUST be able to declare the oldest Facere it needs, and an older Facere MUST fail on that declaration, naming how to upgrade.
