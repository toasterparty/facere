# uv

[uv](https://docs.astral.sh/uv/) manages this project's Python version, virtual environment, and dependencies under the `fac.py` tasks.

## Invoking uv

Call uv through the `tools/uv.sh` wrapper (`tools/uv.ps1` from Windows PowerShell), never as bare `uv`:

```sh
tools/uv.sh add --raw --dev pytest-cov
tools/uv.sh run pytest
```

```powershell
tools/uv.ps1 add --raw --dev pytest-cov
```

The wrapper runs from the repo root and applies `project.env`, as the `fac.py` tasks do, which pins the virtual environment (`build/.venv`) and the bytecode cache (`build/pycache`). A bare `uv` would ignore all of that and create a `.venv` at the repo root, outside the isolated build tree.

## Environment

`build/.venv` installs the project as an editable redirect to the source tree; point your editor's interpreter here.

## The lockfile

`uv.lock` pins the exact resolved versions of every dependency and is committed to the repo. The tasks run `uv run --locked`, which fails if the lockfile is out of date with `pyproject.toml`, so local, CI, and release builds stay identical. A hand edit to `pyproject.toml` leaves the lockfile stale, so change dependencies through uv.

Dependencies in `pyproject.toml` stay unpinned, since the lockfile holds the versions. Pass `--raw` to `add`: uv otherwise writes a `>=` bound, and no setting turns that off.

## Common commands

| Command | Purpose |
| ------- | ------- |
| `tools/uv.sh add --raw --dev <pkg>` | Add a development-only dependency |
| `tools/uv.sh remove --dev <pkg>` | Remove a development-only dependency |
| `tools/uv.sh lock --upgrade` | Upgrade all locked versions (also the `upgrade` task) |
| `tools/uv.sh run <cmd>` | Run a command inside the project environment |
| `tools/uv.sh sync` | Install the locked dependencies |

## Python version

`requires-python` in `pyproject.toml` declares the oldest supported Python. uv resolves an interpreter that satisfies it, installing one if the machine has none, so you do not need a separately installed Python. Set `UV_PYTHON` to test another version, as CI does for each one in its matrix: `UV_PYTHON=3.11 uvx facere test`.
