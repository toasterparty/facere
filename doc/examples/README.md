# Examples

Each directory is a project of its own, run with `uv run fac -C doc/examples/<name>` from the repository's root. Read them in this order, simplest first. A *(planned)* example uses features no release has yet.

1. [`hello-world/`](./hello-world/fac.py) - a C program, as [getting started](../user/1-getting-started.md) finishes it
2. [`c-configurations/`](./c-configurations/README.md) - a C program in debug and release from one table
3. [`static-site/`](./static-site/README.md) - Markdown pages to one directory, with a shared module and a server task
4. [`data-pipeline/`](./data-pipeline/README.md) - separate programs chained through files, using each `fac.run` option
5. [`many-files/`](./many-files/README.md) - 1500 rules, each writing a file of its own
6. [`sum/`](./sum/README.md) *(planned)* - two rules connected by a path, one fetching data that moves
7. [`many-rows/`](./many-rows/README.md) *(planned)* - the same rules as `many-files`, each writing one row of a single file
8. [`http-api/`](./http-api/README.md) *(planned)* - local files and pages published to an HTTP REST API, in one graph
9. [`codegen/`](./codegen/README.md) *(planned)* - generated C sources and headers, from a Python generator and from gperf
10. [`python-app/`](./python-app/README.md) *(planned)* - a uv-managed Python app, linted, tested, and released
11. [`c-server-client/`](./c-server-client/README.md) *(planned)* - a C server and client in three configurations, with a fetched dependency
