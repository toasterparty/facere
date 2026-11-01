# Principles

The project's [requirements](./requirements.md) are derived from these guiding principles.

- The user owns the substance of their project. When they use Facere to build it, they keep every decision about what is built, where it is built to, and how. No principle or requirement can be read as an opinion on something the user owns. Facere owns only the project's dependency graph, and so decides only when each output is built and in what order. Implementation owned by the user is not subject to the principles, and therefore the requirements, defined by the Facere project.
- Facere's scope is building. It does not manage packages, compose projects, or perform any job a rule can do.
- Facere is explicit. It checks every input declared to it and guesses none. The user is responsible for declaring every input.
- Facere is transparent. A tool behaves under Facere as it does from the user's shell.
- Facere can be adopted incrementally. A project can hand it one part of its build at a time.
- Facere is observable. A user can always learn what Facere will do and why without reading its source.
- Facere's interface is intuitive and minimal.
- Facere is plain Python. Builds are configured by Python code rather than environment variables, settings files, or a data format invented by Facere.
- Facere is dependable. Its decisions are deterministic, reproducible, and idempotent, and it never reports success while leaving an output stale.
- Facere is efficient, building exactly what is needed and nothing redundantly.
- Facere is quiet. A successful build shows what the user's own tools report, and Facere's own report fits in a glance.
- From 1.0, Facere is backwards compatible forever, except for behavior its maintainers judge to be a bug.
- Facere behaves the same on every machine, regardless of OS, environment, or job count.
- Facere works offline.
