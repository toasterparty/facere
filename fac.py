"""Looking for an example Facere project? See `doc/examples/hello-world/`.

This file develops Facere itself: run `fac <task>` with a released Facere of at least `MINIMUM_FACERE`.
"""

import glob
import os
import re
import shutil
import tomllib
from functools import cache
from pathlib import Path

import facere as fac

# Read by .github/workflows/ci.yml and .github/workflows/release.yml, so keep it on one line.
MINIMUM_FACERE = "0.2.0"

VERSION_FILE = "src/facere/_version.py"
VERSION_LINE = re.compile(r'^VERSION = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)
VERSION_PARTS = ("major", "minor", "patch")
DIST = "build/dist"
TAGS_FILE = "build/action-tags.txt"

WORKFLOWS = ".github/workflows/*.yml"
ACTION_PIN = re.compile(r"(uses: )([\w.-]+/[\w.-]+)@v(\d+(?:\.\d+){0,2})(?![\w.])")
RELEASE_TAG = re.compile(r"refs/tags/v(\d+)\.(\d+)\.(\d+)$", re.MULTILINE)


# A released Facere runs this file, so a broken tree can still build and test itself.
def _validate_released_facere() -> None:
    source = Path(__file__).resolve().parent / "src"
    if not Path(fac.__file__).resolve().is_relative_to(source):
        return
    raise RuntimeError(
        "this tree's own Facere is running, as from an activated .venv: deactivate it and run the installed `fac`"
    )


def _list_package_files() -> list[str]:
    """Return what the sdist holds, as pyproject.toml's only-include lists it, less caches and build outputs."""
    with open("pyproject.toml", "rb") as file:
        included = tomllib.load(file)["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    paths = ["pyproject.toml", ".gitignore"]
    for top in included:
        for path in [top, *glob.glob(f"{top}/**", recursive=True, include_hidden=True)]:
            parts = Path(path).parts
            if os.path.isfile(path) and "__pycache__" not in parts and "build" not in parts:
                paths.append(Path(path).as_posix())
    return sorted(paths)


def _uv(*args: str, env: dict[str, str] | None = None) -> str:
    return fac.run("uv", *args, env=env)


def _uv_run(*args: str, env: dict[str, str] | None = None) -> str:
    return _uv("run", "--locked", *args, env=env)


@cache
def _fetch_latest_release(repo: str) -> tuple[int, ...]:
    os.makedirs(os.path.dirname(TAGS_FILE), exist_ok=True)
    fac.run("git", "ls-remote", "--tags", "--refs", f"https://github.com/{repo}", stdout=TAGS_FILE)
    with open(TAGS_FILE, encoding="utf-8") as file:
        tags = file.read()
    return max(tuple(map(int, match.groups())) for match in RELEASE_TAG.finditer(tags))


def _bump_action_pins(text: str) -> str:
    """Move each `uses: owner/repo@v<pin>` to the newest release, keeping the pin's precision."""

    def bump(match: re.Match[str]) -> str:
        prefix, repo, pin = match.groups()
        latest = _fetch_latest_release(repo)[: pin.count(".") + 1]
        return f"{prefix}{repo}@v{'.'.join(map(str, latest))}"

    return ACTION_PIN.sub(bump, text)


fac.minimum_version(MINIMUM_FACERE)
_validate_released_facere()
PACKAGE_FILES = _list_package_files()


@fac.task(default=True)
def run(example: fac.Input = "doc/examples/hello-world") -> None:
    _uv_run("fac", "-C", example)


@fac.task
def lint() -> None:
    _uv_run("ruff", "check")
    _uv_run("ruff", "format", "--check")
    _uv_run("ty", "check")


@fac.task
def test() -> None:
    lint()
    _uv_run("pytest")


@fac.task
def coverage() -> None:
    cov_dir = os.path.abspath("build/cov")
    rcfile = os.path.join(cov_dir, "coveragerc")
    if os.path.exists(cov_dir):
        shutil.rmtree(cov_dir)
    os.makedirs(cov_dir)
    with open(rcfile, "w", encoding="utf-8", newline="\n") as file:
        file.write(
            f"[run]\ndata_file = {cov_dir}/.coverage\nsource = facere\nparallel = true\npatch = subprocess\n"
        )
    env = {"COVERAGE_RCFILE": rcfile}
    # The test imports the repo's own fac.py once coverage puts the root on sys.path.
    _uv_run(
        "coverage",
        "run",
        "-m",
        "pytest",
        "-q",
        "-n0",
        "--deselect",
        "test/api/test_api.py::test_importing_fac_py_fails_saying_it_ran_twice",
        env=env,
    )
    _uv_run("coverage", "combine", "-q", env=env)
    _uv_run("coverage", "report", "-m", env=env)


@fac.task
def format_() -> None:
    _uv_run("ruff", "check", "--fix")
    _uv_run("ruff", "format")


@fac.task
def upgrade() -> None:
    _uv("lock", "--upgrade")
    for path in glob.glob(WORKFLOWS):
        with open(path, encoding="utf-8", newline="") as file:
            text = file.read()
        bumped = _bump_action_pins(text)
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(bumped)


@fac.task
def bump(args: fac.Args, version_file: str = VERSION_FILE) -> None:
    """Raise the part of `VERSION` named after --, major, minor, or patch, and zero the parts after it."""
    if len(args) != 1 or args[0] not in VERSION_PARTS:
        raise ValueError(f"bump takes one of {', '.join(VERSION_PARTS)}, not {list(args)}")
    text = fac.read_text(version_file)
    match = VERSION_LINE.search(text)
    if match is None:
        raise ValueError(f"{version_file} holds no line matching {VERSION_LINE.pattern}")
    raised = VERSION_PARTS.index(args[0])
    numbers = [int(number) for number in match.groups()]
    bumped = [*numbers[:raised], numbers[raised] + 1, *[0] * (len(numbers) - raised - 1)]
    version = ".".join(map(str, bumped))
    fac.write_text(version_file, VERSION_LINE.sub(f'VERSION = "{version}"', text))
    print(version)


@fac.rule
def dist(files: list[fac.Input] = PACKAGE_FILES, folder: fac.Output = DIST) -> None:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    _uv("build", "--out-dir", folder)


@fac.task
def publish(folder: fac.Input = DIST) -> None:
    _uv("publish", *sorted(glob.glob(f"{folder}/*")))
