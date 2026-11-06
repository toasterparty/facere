# uv

[uv](https://docs.astral.sh/uv/) manages this project's Python version, virtual environment, and dependencies under the `fac.py` tasks.

## Environments

The project's environment is `.venv` at the repo root, where uv puts it by default, so the tasks, plain `uv` commands, and editors share one environment with no setup. It installs the project as an editable redirect to the source tree; point your editor's interpreter here.

Where any other virtual environment lives depends on who uses it:

- If a person would ever activate it, select it in an editor, or `uv add` to it, it is the project's environment and lives where uv puts it. Never relocate it with `UV_PROJECT_ENVIRONMENT`, since every developer would then have to set the variable to share it.
- If only Facere or a script creates and uses it, as for an isolated tool or a test run under another Python version, it lives in `build/`, so deleting `build/` resets it. Setting `UV_PROJECT_ENVIRONMENT` in the code that creates it is fine, since no person has to remember it.

## The lockfile

`uv.lock` pins the exact resolved versions of every dependency and is committed to the repo. The tasks run `uv run --locked`, which fails if the lockfile is out of date with `pyproject.toml`, so local, CI, and release builds stay identical. A hand edit to `pyproject.toml` leaves the lockfile stale, so change dependencies through uv.

Dependencies in `pyproject.toml` stay unpinned, since the lockfile holds the versions. Pass `--raw` to `add`: uv otherwise writes a `>=` bound, and no setting turns that off.

## Common commands

| Command | Purpose |
| ------- | ------- |
| `uv add --raw --dev <pkg>` | Add a development-only dependency |
| `uv remove --dev <pkg>` | Remove a development-only dependency |
| `uv lock --upgrade` | Upgrade all locked versions (also the `upgrade` task) |

## Python version

`requires-python` in `pyproject.toml` declares the oldest supported Python, and `.python-version` names the one development and the release workflow use. uv installs that interpreter if the machine has none, so you do not need a separately installed Python. Set `UV_PYTHON` to test another version, as CI does for each one in its matrix: `UV_PYTHON=3.11 fac test`.
