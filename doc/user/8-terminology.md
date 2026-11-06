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
| Store *(planned)* | An object defined in a `fac.py` that holds values under keys, such as the rows of one file or the resources of an HTTP REST API, and reads and writes them through its own methods. The filesystem is the store Facere has built in. |
| Virtual output *(planned)* | One key of a store together with its value, named by the store and the key, which a rule writes as it does a file. |
| Virtual input *(planned)* | A virtual output as a rule that reads it declares it. |
| Output | A file, directory, or virtual output a rule writes and Facere tracks, declared in its signature. |
| Fingerprint | A hash of a rule's recipe code and what the rule declares, which decides whether the rule must execute again. |
| Input | A file, directory, or virtual output a rule reads and Facere tracks, declared in its signature or reported by its recipe. |
| Added input *(planned)* | An input a recipe reports after its tool has run, such as a header a depfile lists. |
| Order-only input *(planned)* | A declared input built before its reader's recipe executes, which joins the reader's fingerprint only once that recipe reports reading it. |
| Source | An input no rule outputs, which must therefore exist. |
| Output directory | The directory holding every output, unless a rule names another path, and Facere's state. |
| State | Facere's record of past builds, kept in the output directory. |
| Scratch file | A file a recipe writes in the output directory without declaring it as an output, such as a depfile. |
| Value | Data a recipe reads through a parameter or a module constant, which joins its rule's fingerprint as data, never as a file's content. |
| Stale | Said of a rule that must execute, since the state holds no record of it, its fingerprint differs from the record, or one of its outputs is missing or differs from the record. |
| Up to date | Said of a rule whose fingerprint and output contents match the state's record. |
| Shared module | An ordinary Python module under the root that `fac.py` files import for the code and facts they share, and whose code joins the fingerprint of every rule that reaches it. |
| Target | A name or output path given on the command line, which `fac` builds. |
| Build | To execute the recipe of each stale rule that targets need, and of each task they reach. |
| Batch *(planned)* | A maximal run of consecutive targets that reach no task, which `fac` builds together, in parallel. |
| Group *(planned)* | A named set of targets, such as `all`, built together. |
| Scope *(planned)* | A namespace whose name prefixes every name defined inside it: the directory of each `fac.py`, and each block a `fac.py` opens with `fac.scope`. |
| Name | The dotted string you type to reach a rule, task, group, or scope, such as `server.release`. |
| Pattern *(planned)* | A name in which `*` stands for any one dotted part, such as `*.release`. |
| Default | A rule, task, group, or scope that `fac` builds when given no targets, or that its scope's bare name builds. |
| Configuration | One way of building the same sources, such as debug or release, given an output directory and *(planned)* a scope of its own. |
| Override *(planned)* | A function in a `fac.py` that adjusts rules defined elsewhere which read files under that `fac.py`'s directory. |
| Extension *(planned)* | A Python module that packages rules many projects need, using only Facere's public interface. |

[<- Best practices](./7-best-practices.md)
