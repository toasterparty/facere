# Distribution

The wheel is `py3-none-any`. The scheduler and state are Facere's own from the first release, so neither ninja nor doit is a dependency, even as a stopgap. The shipped extensions ship in the same wheel, each a single file until it needs a second: `c.py` and `c/__init__.py` both import as `facere.c`, so an extension can become a package later without users noticing.

## Install

The package is `facere`, run as `fac`. A second script, `facere`, exists for `uvx facere`, which names the package, because `fac` on PyPI is an unrelated project, and the docs use `fac` everywhere else. An unrelated ptrace-based build tool is also called fac.

Facere runs from an environment of its own, never a project's. `uv tool install facere` once per machine puts `fac` on `PATH`, `uv tool upgrade facere` updates it, CI runs `uvx facere`, and pip users run `pipx install facere`. Running outside the project's environment lets a rule create, sync, or delete that environment, and spares a project that is not Python a `pyproject.toml`. In exchange, collection imports no third-party package, as [collection](./collection.md) describes, so a rule needing a third-party library runs it as a command through the project's environment, and a project accepting a per-machine setup adds one to Facere's own environment with `uv tool install facere --with jinja2`.

The compatibility promise from 1.0 lets one install serve every project. Releases before 1.0 build Facere's own repository and gather feedback. A project needing a newer feature calls `fac.minimum_version("1.4")` at the top of its root `fac.py`, which collection loads first, so an older Facere fails there, naming the command that upgrades it, before any other `fac.py` reaches the missing feature.

## Editors

Facere ships inline types, its decorators typed to return the function unchanged, and a CI check type-checks the docs' examples. An editor resolves `import facere` only from an environment holding it: a Python project adds `facere` to its development dependencies, which nothing else uses, and any other project points its editor at the interpreter `fac --python` prints, which holds everything a `fac.py` can import.

## Docs

Shipping the docs in the wheel gives every install the docs matching its version, and `fac --docs` prints their directory, so an agent finds the docs of the Facere that will run its `fac.py` without the network. They stay in `doc/user/` in the repository, mapped into the package at build time, so there is one source. A CI check fails when a name in `facere.__all__`, a shipped extension's public name, or a flag appears nowhere in the docs.

## Facere's own repository

The package lives under `src/`: Facere builds itself with a pinned release, as [development](../development.md) describes, and a root `facere/` would be a shared module that release shadows, which collection rejects. Core modules carry a leading underscore, so `facere.__all__` stays the only public surface, which the CI check on shipped extensions relies on.

Planned example projects each live in a directory of their own with their own `fac.py`, so a contributor can open one or run it with `fac -C`, and the root's `fac.exclude` keeps them out of Facere's own graph. [`doc/examples/README.md`](../../examples/README.md) lists every example in reading order, simplest first, and changes whenever an example is added, renamed, or removed. Tests copy an example into `tmp_path` before running it, so no run writes into the repository, and write their other projects from a dict in the test body, as pytest's `pytester` does, which keeps input and expectation side by side.
