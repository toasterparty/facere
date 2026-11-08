# Principles

The project's [requirements](./requirements.md) are derived from these guiding principles.

- The user owns the substance of their project. When they use Facere to build it, they keep every decision about what is built, where it is built to, and how. No principle or requirement can be read as an opinion on something the user owns. Facere owns only the project's dependency graph, and so decides only when each output is built and in what order. Implementation owned by the user is not subject to the principles, and therefore the requirements, defined by the Facere project.
- Facere tracks what a project builds at the granularity the user chooses, whatever form the user stores it in. A project never splits its data into files, or merges it into one, only to suit Facere.
- Facere's scope is building. It does not manage packages or compose projects. It takes on a job a rule could do only where nearly every `fac.py` would otherwise write it by hand, and a hand-written version goes wrong without failing, as writing a text file or an archive whose bytes differ between machines does.
- Writing a `fac.py` takes only beginner Python: functions, strings, lists, dicts, decorators, and, for a store, a plain class. Facere's own code may use whatever it needs to keep it that way.
- Facere is explicit. It checks every input declared to it and guesses none. The user is responsible for declaring every input, the programs a recipe runs included.
- Facere is transparent. A tool behaves under Facere as it does from the user's shell.
- Facere can be adopted incrementally. A project can hand it one part of its build at a time.
- Facere is observable. A user can always learn what Facere will do and why without reading its source.
- Facere's interface is intuitive and minimal.
- Facere's failures state the facts: what was attempted, on what, and what happened. They prescribe no fix to the project, since the user owns its substance. A remedy belongs in a message only where Facere itself knows it:
    - the failure is the absence of an action only the user can perform, so the message names it, such as upgrading Facere
    - Facere owns the rule the `fac.py` broke, so the message names what in Facere's interface satisfies it, such as the parameter to declare
    - a name is a typo, so the message names its nearest valid match
- Facere is plain Python. Builds are configured by Python code rather than environment variables, settings files, or a data format invented by Facere.
- Facere is dependable. Its decisions are deterministic, reproducible, and idempotent, and it never reports success while leaving an output stale.
- Facere is efficient, building exactly what is needed and nothing redundantly.
- Facere is quiet. A successful build shows what the user's own tools report, and Facere's own report fits in a glance.
- From 1.0, Facere is backwards compatible forever, except for behavior its maintainers judge to be a bug.
- Facere behaves the same on every machine, regardless of OS, environment, or job count.
- Facere works offline.
