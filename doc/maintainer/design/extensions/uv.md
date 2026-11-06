# uv projects

`facere.uv` runs a uv project's tools from rules and tasks. This repository's own use of uv is in [uv](../../uv.md) instead.

## Requirements

- A rule running a tool from a uv project's dependencies MUST see an environment matching the lockfile, even after an earlier rule or task in the same invocation rewrote it.
- The project's Python and environment MUST be uv's, never Facere's own.
- Running a project's tool MUST take no more than running a program on `PATH` does.

## API

| Name | Provides |
|---|---|
| `Project(path=".", venv=None, editable=True, env=None)` | a uv project whose `pyproject.toml` lies in `path`, relative to the calling `fac.py`. `venv` places a venv only Facere uses, such as a release build's, in the output directory instead of uv's default `.venv`, `editable=False` installs the project as a real package, as Nuitka needs, and `env` adds variables to every command it runs |
| `.inputs` | the project's `pyproject.toml` and `uv.lock`, for a rule whose tools come from the project |
| `.run(*args, **kwargs)` | in a recipe, the command run through `uv run --locked`, which syncs the environment to the lockfile first, taking `fac.run`'s keyword arguments |

```python
@dataclass
class Project:
    path: str = "."
    venv: str | None = None
    editable: bool = True
    env: dict[str, str] | None = None

    def __post_init__(self):
        self.path = fac.root(self.path)
        if self.venv:
            self.venv = fac.root(self.venv)

    @property
    def inputs(self):
        return [
            fac.from_root(posixpath.normpath(f"{self.path}/{name}"))
            for name in ("pyproject.toml", "uv.lock")
        ]

    def run(self, *args, env=None, **kwargs):
        variables = {**(self.env or {}), **(env or {})}
        if self.venv:
            variables["UV_PROJECT_ENVIRONMENT"] = self.venv
        options = [
            "--locked",
            "--project",
            self.path,
            *([] if self.editable else ["--no-editable"]),
        ]
        return fac.run("uv", "run", *options, *args, env=variables, **kwargs)
```

Every command runs under the uv on `PATH`, the user's own, which they keep current. A `Project` is a dataclass, so a recipe receives it as a value whose fields join the fingerprint, and it stores root-relative paths, since a recipe executes at the root. `--locked` fails a command when `uv.lock` disagrees with `pyproject.toml`, rather than rewriting the lockfile mid-run.

A task needs no `.inputs`, since it always executes and `.run` syncs anyway. A rule needing a third-party library at build time runs it through `.run` too, as in `project.run("python", "-m", "tool")`.

## Open risks

- **Collecting the project's own package** works only while its `__init__.py` imports nothing outside the standard library, since collection runs in Facere's environment rather than the project's.
- **Two Facere versions.** A type checker resolves `import facere` in a `fac.py` through the project's development dependency, which may be older or newer than the Facere on `PATH`, so the checker and `fac` can disagree on which names exist.
- **Upgrading Facere** happens outside `fac`. A recipe running `uv tool upgrade facere` would replace the Facere running it, which Windows refuses.
