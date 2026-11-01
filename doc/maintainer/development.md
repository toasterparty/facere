# Development

On Windows, run this once to install Git bash and GNU make and add bash to your PATH:

```powershell
./tools/install-bash.ps1
```

On Linux/macOS, confirm `make` is installed (it usually is).

## Make targets

Every target but `clean` provisions the environment first, so there is no separate setup step.

| Command | Description |
| ------- | ----------- |
| `make run` | Build `examples/hello` with Facere from source |
| `make test` | Lint, then run the tests (`tests/`) |
| `make lint` | Check formatting, lint, and types |
| `make format` | Auto-format and fix lint |
| `make upgrade` | Upgrade uv (plus Git bash and make on Windows) and the locked dependencies |
| `make publish` | Build and publish the PyPI package (CI only) |
| `make clean` | Delete `build/`, which holds every generated file: the venv, caches, and build outputs |

Change dependencies through `tools/uv.sh`, never by editing `pyproject.toml`, as [uv.md](./uv.md) explains.
