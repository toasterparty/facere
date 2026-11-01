# Development

Facere builds itself with its latest release, from the root `fac.py`. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), or run `tools/install.sh`, then run each task with `uvx facere <task>`. After `uv tool install facere`, `fac <task>` does the same. Every task provisions the environment first, so there is no separate setup step.

| Task | Description |
| ---- | ----------- |
| `run` | Build `examples/hello` with Facere from source. The default |
| `test` | Lint, then run the tests (`tests/`) |
| `lint` | Check formatting, lint, and types |
| `format` | Auto-format and fix lint |
| `upgrade` | Upgrade uv and the locked dependencies |
| `publish` | Build and publish the PyPI package (CI only) |

`build/` holds every generated file: the venv, caches, and build outputs. Delete it to start over.

The tasks run the tree's own Facere through `uv run --locked fac`, while `uvx facere` runs the latest release. Keep the root `fac.py` to what that release supports, since CI runs it with that release.

Change dependencies through `tools/uv.sh`, never by editing `pyproject.toml`, as [uv.md](./uv.md) explains.
