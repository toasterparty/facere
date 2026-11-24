# Development

Install [git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/), which also installs the Python Facere needs. Then install Facere the way its users do, clone the repo, and build the example:

```sh
uv tool install facere
git clone git@github.com:toasterparty/facere.git
cd facere
fac example
```

The first `fac example` creates the project's environment in `.venv` and downloads dependencies, so it takes a minute. A bare `fac` lists the tasks.

Two Facere versions run in a checkout, and the command decides which:

| Command | Facere | Use it for |
| ------- | ------ | ---------- |
| `fac <task>` | The latest release, installed with `uv tool install facere` | The root `fac.py`: `fac test`, `fac format`, and the other tasks `fac` lists |
| `uv run fac -C <project>` | This tree's `src/`, the code under development | Any project that exercises a change, such as `doc/examples/*` |

The split lets a broken tree still test itself. The root `fac.py` therefore refuses the tree's own Facere, which is what a bare `fac` resolves to wherever `.venv` is activated, as in a VS Code terminal once the editor's interpreter is set. Deactivate it there. VS Code's terminals leave it inactive, as below.

An example may use a feature no release has yet, so the installed `fac` fails on it with an `AttributeError` on `facere`. Run it with `uv run fac -C <project>` instead, as the `example` task does for `doc/examples/my-site`.

`MINIMUM_FACERE` in the root `fac.py` names the oldest release it runs on, and an older `fac` fails with the command that upgrades it. CI tests on both that release and the latest. Adopt a Facere feature in the root `fac.py` only once a release has it, and raise `MINIMUM_FACERE` to that release. A recipe cannot read a global naming a path outside the output directory, so the root `fac.py` passes paths such as `VERSION_FILE` as parameter defaults.

CI and release logic lives in the root `fac.py` and `release.py` so a developer can run it:

- A workflow's `run:` holds only what is specific to CI. Anything else is a `fac` task or a script.
- Prefer Python to shell beyond trivial logic, and `python -c` only for a trivial line.

VS Code suggests the extensions this project uses, from `.vscode/extensions.json`, and `.vscode/settings.json` keeps its terminals from activating `.venv`. For completion and hover docs, select `.venv` as the interpreter with `Python: Select Interpreter`. Its editable install points Pylance at `src/`, so `import facere` resolves to the tree's code from the root `fac.py`, every example, and the tests. Personal settings belong in your VS Code user settings. Linting and type checks stay `fac lint`'s job, through ruff and ty.

`build/` holds the caches and build outputs, and `.venv` the project's environment, as [uv](./uv.md) explains. Delete both to start over.

## Testing

`fac test` lints, then runs pytest under xdist. `fac test -- --long` adds the tests that take minutes, among them the [oracle](./oracle.md)'s shards.

- Each pytest run numbers its own directory under `build/test/tmp/`, keeping the last three, so runs in one tree can overlap. A `--basetemp` given by hand is wiped at startup, so give each concurrent run its own.
- `fac coverage` measures coverage, subprocesses included. It runs serially because `-p no:xdist` breaks on the `-n auto` in `addopts`. Without `PYTHONSAFEPATH`, `coverage run -m` puts the repo root on `sys.path`, so a fixture's `import fac` would import the root `fac.py`. Coverage never traces an audit hook, so `_undeclared._on_audit` reads as uncovered though `test/api/test_undeclared_paths.py` exercises it.
- `test/test_repo.py` compares facts several config files repeat, such as the CI Python matrix against `.python-version`. Update both sides of a failure together. It skips in an sdist, which holds no `.github/`.
- `my-site`'s `fac.py` must equal the finished `fac.py` in `doc/user/1-getting-started.md`, which `test/examples/test_my_site.py` checks, and the page's earlier snippets grow toward it, so edit them together.
- The example tests edit each example's `fac.py` by exact string through `edit(path, old, new)`, so search them for a line before rewriting it in an example. `edit` replaces every occurrence, so a comment quoting that string is rewritten too, and can keep the test passing after the code line is gone.
- A test fixture naming an undeclared path must name it in the recipe's body. As a module constant or an unannotated value it fails collection instead, before the undeclared-path check can run.
- A fixture's parameter cannot be called `name`, or anything else `@fac.rule` takes as an option.
- A test of rules executing at once makes each recipe wait for a file the other writes, with a deadline, so it fails rather than hangs when they do not overlap. Sleeping and hoping for overlap is flaky.
- A watch never ends by itself, so a test of `fac --watch` stops it as the test ends, as the fixture in `test/cli/test_watch.py` does, and waits on the lines it prints and the files a cycle writes, each with a deadline.
- A test that needs a terminal runs on a pty from `test/cli/terminal.py`, with stdin on it too, since a command that holds the terminal needs both stdin and stderr to be terminals.
- On a cold uv cache the first compile of a C example installs zig while it executes. Its headers lie outside the root, whose first reports are trusted, so the example tests need no install first. Check with `UV_CACHE_DIR=$(mktemp -d)`.
- [Windows](./windows.md) has its own process, signal, and console behavior to know before testing there.

### Timestamps in tests

- `fac` run in-process reaches its first recipe within the timer tick of a file the test just wrote about a third of the time, where a `fac` process never does. Every file a test writes is therefore racy in the hash cache, and reread.
- A test that reaches the cache's trusted path, by patching `facere._build.time` to start the clock later, must wait for the file system's tick before an edit, or the edit can share its stamp with the build that just read the file. `wait_for_later_change_time` in `test/helpers.py` does that.
- ctime cannot be set back, so `os.utime` cannot age a fixture.
- A fixture that stands in for an editor saving a file during a recipe writes a scratch file and moves it onto the path with `os.replace`. Writing the path from the recipe's own Python marks it as the recipe's file, which the check exempts, and on Windows a file only moved keeps its mtime and creation time.
- A fsync outlasts a timer tick, so records fsynced under `build/` on ext4 once hid timing bugs that tmpfs showed. Run timing-sensitive tests on tmpfs too.

## Lint and types

- `ruff format --check` also formats the Python code blocks in Markdown under `doc/`, so a long line in a doc's sample fails `fac test`. `fac format` reflows it to the 100-column limit.
- Ruff's SIM115 accepts `files.enter_context(open(...))` only lexically inside the `with contextlib.ExitStack()` block. Moving the `open` calls into a helper that takes the stack trips it.
- A planned example's `fac.py` is excluded from ruff and ty in `pyproject.toml`, file by file where the example also holds stdlib-only code, such as `doc/examples/http-api/tools/`, which stays checked.
- ty checks Windows typing too, so a `sys.platform == "win32"` test that looks redundant may be what lets it accept a POSIX-only call such as `os.killpg`.
- ty rejects narrowing an inherited mutable attribute by annotation, such as `server: MyServer` on a `BaseHTTPRequestHandler` subclass (`invalid-mutable-override`). Read it through a property that asserts `isinstance` instead.
- ty narrows `isinstance(x, dict)` to `Top[dict[Unknown, Unknown]]`, which no `dict[K, V]` parameter accepts, since `dict` is invariant. Annotate the parameter `Mapping[...]` instead.
- ty rejects `not x` on a `tuple[...] | None` and asks for `is None` or `bool(x)`, so `not bool(task_args)` in `_build.py` is deliberate.
- ty rejects returning or assigning `sqlite3`'s `fetchall()` as anything narrower than `list[Any]` (`unsound-return-statement`), so `_state._fetch` returns `list[Any]`.
- ty checks against the project's environment, so it skips a script in `tools/` that declares its own dependencies inline, such as click, and runs through `uv run`. Ruff checks every script.
