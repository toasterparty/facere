# Development

Install [git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/), which also installs the Python Facere needs. Then install Facere the way its users do, clone the repo, and build the example:

```sh
uv tool install facere
git clone git@github.com:toasterparty/facere.git
cd facere
fac
```

The first `fac` creates the project's environment in `.venv` and downloads dependencies, so it takes a minute.

| Task | Description |
| ---- | ----------- |
| `example` | Build `doc/examples/my-site` with Facere from source. The default |
| `test` | Lint, then run the tests (`test/`). `fac test -- --long` adds those that take minutes, such as the differential test in `test/oracle/` on new seeds |
| `ci` | `test`, then check the built wheel: what a pull request must pass |
| `test_sdist` | Run the tests from the unpacked sdist |
| `lint` | Check formatting, lint, and types |
| `coverage` | Run the tests serially under coverage, subprocesses included, and print the report |
| `format` | Auto-format and fix lint |
| `upgrade` | Upgrade the locked dependencies and the GitHub Actions pinned in `.github/` |
| `dist` | Build the sdist and wheel into `build/dist/` |
| `build_release` | Build a release of a [release type](./releasing.md) in a scratch clone: `fac build_release -- Minor` |
| `push_release` | Push what `build_release` built, atomically |
| `publish_release` | Upload what `build_release` built to PyPI |

Two Facere versions run in a checkout, and the command decides which:

| Command | Facere | Use it for |
| ------- | ------ | ---------- |
| `fac <task>` | The latest release, installed with `uv tool install facere` | The root `fac.py`: `fac test`, `fac format`, and the other tasks above |
| `uv run fac -C <project>` | This tree's `src/`, the code under development | Any project that exercises a change, such as `doc/examples/*` |

The split lets a broken tree still test itself. The root `fac.py` therefore refuses the tree's own Facere, which is what a bare `fac` resolves to wherever `.venv` is activated, as in a VS Code terminal once the editor's interpreter is set. Deactivate it there. VS Code's terminals leave it inactive, as below.

An example may use a feature no release has yet, so the installed `fac` fails on it with an `AttributeError` on `facere`. Run it with `uv run fac -C <project>` instead, as the `example` task does for `doc/examples/my-site`.

`MINIMUM_FACERE` in the root `fac.py` names the oldest release it runs on, and an older `fac` fails with the command that upgrades it. CI tests on both that release and the latest. Adopt a Facere feature in the root `fac.py` only once a release has it, and raise `MINIMUM_FACERE` to that release.

CI and release logic lives in the root `fac.py` and `release.py` so a developer can run it:

- A workflow's `run:` holds only what is specific to CI. Anything else is a `fac` task or a script.
- Prefer Python to shell beyond trivial logic, and `python -c` only for a trivial line.

VS Code suggests the extensions this project uses, from `.vscode/extensions.json`, and `.vscode/settings.json` keeps its terminals from activating `.venv`. For completion and hover docs, select `.venv` as the interpreter with `Python: Select Interpreter`. Its editable install points Pylance at `src/`, so `import facere` resolves to the tree's code from the root `fac.py`, every example, and the tests. Personal settings belong in your VS Code user settings. Linting and type checks stay `fac lint`'s job, through ruff and ty.

`build/` holds the caches and build outputs, and `.venv` the project's environment, as [uv](./uv.md) explains. Delete both to start over.
