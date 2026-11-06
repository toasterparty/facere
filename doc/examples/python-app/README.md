# Example: a Python app

> **Status:** planned. This example uses `facere.uv`, `fac.give_lock`, `fac.write_archive`, the `clear=` option of `fac.rule`, and the `inherit=` option of `fac.run`, which no release supports yet, so it does not run on the current release.

A Python app with a CLI and an optional tkinter GUI, managed by uv, linted with ruff and ty, tested with pytest, released as Nuitka standalone executables for Windows, macOS, and Linux, and optionally published to PyPI. It is the Facere version of a Makefile project that needed Git bash on Windows, a wrapper script to apply environment settings to uv, and an install stamp. The design is in [Design](../../maintainer/design/README.md).

Only [`fac.py`](./fac.py) is included. The rest of the project is an ordinary uv package:

```
fac.py                          every rule and task, replacing the Makefile
pyproject.toml                  facere added to the dev dependencies, for the editor and ty
.github/workflows/ci.yml        uvx facere test
.github/workflows/release.yml   uv version --bump, uvx facere release, uvx facere publish
.vscode/tasks.json              fac run, fac test, fac lint, fac format, fac upgrade, fac release, fac clean
hello_world/                    the package, its __init__.py defining PRODUCT_NAME
test/
```

The Makefile, `project.env`, and all six scripts in `tools/` are gone. Facere spawns no shell, so Windows needs no Git bash, and settings are Python values, so uv needs no wrapper to apply them.

## fac.py

The project's metadata stays in `pyproject.toml`, read at collection, so a version bump reaches the archive's name and the Windows version resource as values, and the release re-executes. `PRODUCT_NAME` comes from importing the package itself, which collection finds at the root. `SHOW_CONSOLE` and `COMPANY` were environment settings and are now constants, and the copyright year is a value too, so the first Windows release of a new year re-executes.

Every tool from the project's dependencies runs through [uv projects](../../maintainer/design/extensions/uv.md), whose `run` syncs the venv to the lockfile before the tool starts, so the tools always match it, even straight after `fac upgrade`. `release` inputs `DEV.inputs`, the project's `pyproject.toml` and `uv.lock`, so a dependency change rebuilds it. The development venv is uv's default `.venv` at the root, since a `uv add` typed by hand reads no `fac.py` and would make one there anyway. The release venv in `build/release/` is one only Facere's rules and tasks touch, so `fac clean` takes it.

`lint` and `test` are tasks, since their point is checking the code, not producing a file, so each runs whenever named and reports live, and `test` calls `lint` first, as `make test` did. Recipes read module constants such as `DEV` and `NAME` directly, while `release` calls `fac.out("dist")` in its body, where it returns a root-relative path, since a module constant reaches a recipe unchanged. `run` is the default, so a bare `fac` opens the app, as `make` did. Like every task it has the terminal, and it passes on the whole environment, since a GUI needs the display and session variables, and it releases the lock before opening the window, so a lint-on-save run proceeds while the app stays open. `fac.write_archive` replaces the release script's bash, packing Nuitka's output directory straight into the archive under the app's name, with the same bytes for the same files, so a re-execute leaves the archive's consumers alone. `pypi` sets `clear=True`, since `uv build` would otherwise leave an old version's wheel beside the new one for `publish` to upload. `publish` passes on only the variables trusted publishing reads, so run outside CI, uv asks for credentials at the terminal.

## Runs

| Action | Executes | Why |
|---|---|---|
| `fac` | `run` | The default. Each `uv run` syncs `.venv` first |
| `fac test` | `test`, linting first | A task runs whenever requested |
| `fac upgrade test` | `upgrade`, `test` | `uv run --locked` syncs the venv to the new lockfile before each tool runs |
| `fac lint` while `fac run` has the app open | `lint` | `run` released the lock |
| `fac release` | `release` | Nothing is recorded yet |
| `uv version --bump patch`, then `fac release` | `release` | `pyproject.toml` changed, and with it the archive's name |
| `fac publish`, in CI | `pypi`, `publish` | `publish` inputs `pypi`'s directory |
| `fac clean` | `clean` | `.venv` at the root stays |

## Rough edges

- **Collecting the package** works only while its `__init__.py` imports nothing outside the standard library, since collection runs in Facere's environment rather than the project's.
- **Two Facere versions.** `ty check` covers `fac.py` and resolves `import facere` only through the development dependency, which may be older or newer than the Facere on `PATH`, so the checker and the run can disagree on which names exist.
- **Upgrading Facere** happens outside `fac`. A recipe running `uv tool upgrade facere` would replace the Facere running it, which Windows refuses.
- **Nuitka's own downloads**, such as its dependency walker, fill a cache Facere does not track and touch the network the first time a machine runs `release`.
