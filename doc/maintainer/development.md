# Development

Install [git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/), which also installs the Python Facere needs and, for the example, a C compiler. Then install Facere the way its users do, clone the repo, and build the example:

```sh
uv tool install facere
git clone git@github.com:toasterparty/facere.git
cd facere
fac
```

The first `fac` creates the project's environment in `.venv` and downloads dependencies, so it takes a minute.

| Task | Description |
| ---- | ----------- |
| `run` | Build `doc/examples/hello-world` with Facere from source. The default |
| `test` | Lint, then run the tests (`test/`) |
| `lint` | Check formatting, lint, and types |
| `coverage` | Run the tests serially under coverage, subprocesses included, and print the report |
| `format` | Auto-format and fix lint |
| `upgrade` | Upgrade the locked dependencies and the GitHub Actions pinned in `.github/workflows/` |
| `bump` | Raise `VERSION`: `fac bump -- major`, `minor`, or `patch` |
| `dist` | Build the sdist and wheel into `build/dist/` |
| `publish` | Publish `build/dist/` to PyPI, building it first if stale (CI only) |

Two Facere versions run in a checkout, and the command decides which:

| Command | Facere | Use it for |
| ------- | ------ | ---------- |
| `fac <task>` | The latest release, installed with `uv tool install facere` | The root `fac.py`: `fac test`, `fac format`, and the other tasks above |
| `uv run fac -C <project>` | This tree's `src/`, the code under development | Any project that exercises a change, such as `doc/examples/*` |

The split lets a broken tree still test itself. The root `fac.py` therefore refuses the tree's own Facere, which is what a bare `fac` resolves to wherever `.venv` is activated, as in a VS Code terminal once the editor's interpreter is set. Deactivate it there, or keep VS Code from activating it, as below.

An example may use a feature no release has yet, so the installed `fac` fails on it, as `fac -C doc/examples/many-files` does with `module 'facere' has no attribute 'sources'`. Run it with `uv run fac -C doc/examples/many-files` instead. The `run` task does the same for `doc/examples/hello-world`.

`MINIMUM_FACERE` in the root `fac.py` names the oldest release it runs on, and an older `fac` fails with the command that upgrades it. CI tests on both that release and the latest. Adopt a Facere feature in the root `fac.py` only once a release has it, and raise `MINIMUM_FACERE` to that release.

VS Code suggests the extensions this project uses, from `.vscode/extensions.json`. For completion and hover docs, select `.venv` as the interpreter with `Python: Select Interpreter`. Its editable install points Pylance at `src/`, so `import facere` resolves to the tree's code from the root `fac.py`, every example, and the tests. Set these in `.vscode/settings.json`, which stays untracked:

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.terminal.activateEnvironment": false,
    "python.analysis.typeCheckingMode": "standard"
}
```

On Windows the interpreter is `.venv/Scripts/python.exe`. Linting and type checks stay `fac lint`'s job, through ruff and ty.

`build/` holds the caches and build outputs, and `.venv` the project's environment, as [uv](./uv.md) explains. Delete both to start over.
