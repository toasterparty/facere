# Terminology

Each term is defined using only the terms above it, so reading top to bottom never meets a term before its definition.

| Term | Definition |
| --- | --- |
| Facere | The project name derived from the *infinitive* Latin verb for make. |
| `fac` | The command and module alias derived from the *imperative* Latin verb for make. |
| Project | The code, tools, and documentation for producing a piece of software, typically one git repository. |
| `fac.py` | A Python file holding a project's build definitions, which `fac` finds and loads. |
| Root | The directory whose `fac.py` defines the project, and the one `fac` starts in unless a flag names another. |
| Invocation | One run of `fac`, from start to exit. |
| Rule | A function in a `fac.py`, decorated with `@fac.rule`, whose signature declares the files it reads and at least one file it writes. |
| Task | A function in a `fac.py`, decorated with `@fac.task`, that reads files as a rule does but writes none Facere tracks, and executes whenever requested. |
| Recipe | The Python function a rule or task executes, together with the commands it runs. |
| Command | A program a recipe runs through `fac.run`, with its arguments. |
| Collection | Loading every `fac.py` and defining its rules and tasks, before any recipe executes. |
| Output | A file or directory a rule writes and Facere tracks, declared in its signature. |
| Fingerprint | A hash of everything Facere observes that can change a rule's outputs, except inherited environment variables. |
| Input | A file or directory a rule reads and Facere tracks, declared in its signature or reported by its recipe. The rule that outputs it executes first. |
| Added input | An input a recipe reports after its tool has run, such as a header a depfile lists. |
| Order-only input | A declared input built before its reader's recipe executes, which joins the reader's fingerprint only once that recipe reports reading it. |
| Source | An input no rule outputs, which must therefore exist. |
| Output directory | The directory holding every output, unless a rule names another path, and Facere's state. |
| State | Facere's record of past builds, kept in the output directory. Deleting the directory forgets it. |
| Scratch file | A file a recipe writes in the output directory without declaring it as an output, such as a depfile, named after one of its rule's outputs. |
| Value | Data a recipe reads through a parameter or a module constant, which joins its rule's fingerprint as data, never as a file's content. |
| Stale | Said of a rule the state holds no record of, or whose fingerprint or output content, a missing output included, differs from the record. |
| Up to date | Said of a rule whose fingerprint and output contents match the state's record. |
| Shared module | An ordinary Python module under the root that `fac.py` files import for the code and facts they share, and whose code joins the fingerprint of every rule that reaches it. |
| Target | A name or output path given on the command line, which `fac` builds. |
| Build | To execute the recipe of each stale rule that targets need, and of each task they reach. |
| Batch | A maximal run of consecutive targets that reach no task, which `fac` builds together, in parallel. |
| Group | A named set of targets, such as `all`, built together. |
| Scope | A namespace whose name prefixes every name defined inside it: the directory of each `fac.py`, and each block a `fac.py` opens with `fac.scope`. |
| Name | The dotted string you type to reach a rule, task, group, or scope, such as `server.release`. |
| Pattern | A name in which `*` stands for any one dotted part, such as `*.release`. |
| Default | A rule, task, group, or scope that `fac` builds when given no targets, or that its scope's bare name builds. |
| Configuration | One way of building the same sources, such as debug or release, given a scope and output directory of its own. |
| Override | A function in a `fac.py` that adjusts rules defined elsewhere which read files under that `fac.py`'s directory. |
| Extension | A Python module that packages rules many projects need, using only Facere's public interface. |
