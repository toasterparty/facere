"""Looking for an example Facere project? See `doc/examples/hello-world/`.

This file develops Facere itself: run `fac <task>` with a released Facere of at least `MINIMUM_FACERE`.
"""

import glob
import os
import re
import shutil
import tempfile
import tomllib
from functools import cache
from pathlib import Path

import facere as fac
import release

# Read by .github/actions/setup-fac/action.yml, so keep it on one line.
MINIMUM_FACERE = "0.2.0"

VERSION_FILE = "src/facere/_version.py"
VERSION_LINE = re.compile(r'^VERSION = "(.+)"$', re.MULTILINE)
DIST = "build/dist"
CAPTURE_FILE = "build/captured.txt"

RELEASE_DIR = "build/release"
RELEASE_DIST = f"{RELEASE_DIR}/dist"
RELEASE_BUNDLE = f"{RELEASE_DIR}/release.bundle"
RELEASE_VERSION = f"{RELEASE_DIR}/version.txt"
RELEASE_AUTHOR = "github-actions[bot]"
RELEASE_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
PYPI_INDEX = "https://pypi.org/simple/"

ACTION_FILES = ".github/**/*.yml"
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


# fac.run(quiet=True) captures in a task only in a release newer than MINIMUM_FACERE.
def _capture(*args: str) -> str:
    os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)
    fac.run(*args, stdout=CAPTURE_FILE)
    return fac.read_text(CAPTURE_FILE)


@cache
def _fetch_latest_release(repo: str) -> tuple[int, ...]:
    tags = _capture("git", "ls-remote", "--tags", "--refs", f"https://github.com/{repo}")
    return max(tuple(map(int, match.groups())) for match in RELEASE_TAG.finditer(tags))


def _bump_action_pins(text: str) -> str:
    """Move each `uses: owner/repo@v<pin>` to the newest release, keeping the pin's precision."""

    def bump(match: re.Match[str]) -> str:
        prefix, repo, pin = match.groups()
        latest = _fetch_latest_release(repo)[: pin.count(".") + 1]
        return f"{prefix}{repo}@v{'.'.join(map(str, latest))}"

    return ACTION_PIN.sub(bump, text)


def _parse_version(text: str) -> str:
    match = VERSION_LINE.search(text)
    if match is None:
        raise ValueError(f"no line matching {VERSION_LINE.pattern} in:\n{text}")
    return str(match[1])


def _write_version(version_file: str, version: str) -> None:
    text = fac.read_text(version_file)
    fac.write_text(version_file, VERSION_LINE.sub(f'VERSION = "{version}"', text))


def _parse_release_type(args: tuple[str, ...]) -> str:
    if len(args) != 1:
        raise ValueError(f"expected one of {', '.join(release.CHOICES)} after --, not {list(args)}")
    return args[0]


def _validate_wheel(folder: str, version: str) -> None:
    (wheel,) = glob.glob(f"{folder}/*.whl")
    reported = _capture("uvx", "--isolated", "--from", wheel, "fac", "--version").strip()
    if reported != version:
        raise ValueError(f"{wheel} reports version {reported}, not {version}")


def _build_release_in(scratch: str, version: str, version_file: str) -> None:
    tag = f"v{version}"
    message = f"Release {tag}"
    git = [
        "git",
        "-C",
        scratch,
        "-c",
        f"user.name={RELEASE_AUTHOR}",
        "-c",
        f"user.email={RELEASE_EMAIL}",
    ]
    fac.run("git", "clone", "--quiet", ".", scratch)
    _write_version(os.path.join(scratch, version_file), version)
    fac.run(git, "commit", "--quiet", "--all", "--message", message)
    fac.run(git, "tag", "--annotate", "--message", message, tag)
    fac.run(git, "bundle", "create", "--quiet", os.path.abspath(RELEASE_BUNDLE), f"refs/tags/{tag}")
    _uv("build", scratch, "--out-dir", RELEASE_DIST)
    _validate_wheel(RELEASE_DIST, version)
    fac.write_text(RELEASE_VERSION, version)


fac.minimum_version(MINIMUM_FACERE)
_validate_released_facere()
PACKAGE_FILES = _list_package_files()


@fac.task(default=True)
def example(project: fac.Input = "doc/examples/hello-world") -> None:
    _uv_run("fac", "-C", project)


@fac.task
def lint() -> None:
    _uv_run("ruff", "check")
    _uv_run("ruff", "format", "--check")
    _uv_run("ty", "check")
    _uv_run("ty", "check", "--python-platform", "win32")


@fac.task
def test() -> None:
    lint()
    _uv_run("pytest")


@fac.task
def ci(folder: fac.Input = DIST, version_file: fac.Input = VERSION_FILE) -> None:
    """Run what a pull request must pass: `test`, then a check of the wheel `dist` builds."""
    test()
    _validate_wheel(folder, _parse_version(fac.read_text(version_file)))


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
    for path in glob.glob(ACTION_FILES, recursive=True):
        with open(path, encoding="utf-8", newline="") as file:
            text = file.read()
        bumped = _bump_action_pins(text)
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(bumped)


@fac.rule
def dist(files: list[fac.Input] = PACKAGE_FILES, folder: fac.Output = DIST) -> None:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    _uv("build", "--out-dir", folder)


@fac.task
def build_release(args: fac.Args, version_file: str = VERSION_FILE) -> None:
    """Build a release of the type named after -- in a scratch clone, writing only under `build/`."""
    choice = _parse_release_type(args)
    current = _parse_version(_capture("git", "show", f"HEAD:{version_file}"))
    version = release.calc_next_version(current, choice)
    release.validate_release(version, choice, _capture("git", "branch", "--show-current").strip())
    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR)
    os.makedirs(RELEASE_DIR)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        _build_release_in(scratch, version, version_file)


@fac.task
def push_release() -> None:
    """Push what `build_release` built: the branch and tag land together, or a moved branch rejects both."""
    tag = f"v{fac.read_text(RELEASE_VERSION)}"
    branch = _capture("git", "branch", "--show-current").strip()
    fac.run("git", "fetch", "--quiet", RELEASE_BUNDLE, f"refs/tags/{tag}:refs/tags/{tag}")
    fac.run(
        "git",
        "push",
        "--atomic",
        "origin",
        f"{tag}^{{commit}}:refs/heads/{branch}",
        f"refs/tags/{tag}",
    )


@fac.task
def publish_release() -> None:
    """Upload what `build_release` built, skipping files the index already holds."""
    files = sorted(glob.glob(f"{RELEASE_DIST}/*"))
    if not files:
        raise FileNotFoundError(f"no files to publish in {RELEASE_DIST}")
    _uv("publish", "--check-url", PYPI_INDEX, *files)
