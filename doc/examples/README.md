# Examples

Each directory is a project of its own, run with `uv run fac -C doc/examples/<name>` from the repository's root. Read them in this order, simplest first. `hello-world`, `c-configurations`, `codegen`, and `c-tools` use features new in 0.4. A *(planned)* example uses features no version has yet.

1. [`hello-world/`](./hello-world/fac.py) - a C program, as [getting started](../user/1-getting-started.md) finishes it: `fac.sources`, `each=`, depfiles through `fac.add_inputs` and `fac.c.makefile_deps`, a value read from the environment while `fac.py` loads, and a task taking `fac.Args`
2. [`c-configurations/`](./c-configurations/README.md) - a C program in debug and release from one table: rules built in loops, and a path as a target
3. [`static-site/`](./static-site/README.md) - Markdown pages to one directory: a shared module, a directory output, `fac.minimum_version`, and a server task
4. [`data-pipeline/`](./data-pipeline/README.md) - separate programs chained through files: each `fac.run` option, `fac.env`, several outputs from one rule, a `str` value, and an output that comes out the same
5. [`many-files/`](./many-files/README.md) - 1500 rules, each writing a file of its own, and a task taking its own options
6. [`codegen/`](./codegen/README.md) - generated C sources and headers, from a Python generator and from gperf: `fac.OrderOnly`, the undeclared-path and ordering failures, and a new file that could shadow a header
7. [`c-tools/`](./c-tools/README.md) - the tools around a C build: formatter, analyzer, size summary, disassembly, valgrind, a version bump, and flashing, with a value for every rule of one function, target order, and the flags `-v`, `-q`, and `--out`
8. [`sum/`](./sum/README.md) *(planned)* - two rules connected by a path, one fetching data that moves
9. [`many-rows/`](./many-rows/README.md) *(planned)* - the same rules as `many-files`, each writing one row of a single file
10. [`http-api/`](./http-api/README.md) *(planned)* - local files and pages published to an HTTP REST API, in one graph
11. [`python-app/`](./python-app/README.md) *(planned)* - a uv-managed Python app, linted, tested, and released
12. [`c-server-client/`](./c-server-client/README.md) *(planned)* - a C server and client in three configurations, with a fetched dependency
