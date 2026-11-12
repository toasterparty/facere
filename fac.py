"""Looking for an example Facere project? See `doc/examples/my-site/`.

This file develops Facere itself: run `fac <task>` with a released Facere of at least `MINIMUM_FACERE`.
"""

import glob
import inspect
import os
import re
import shutil
import tarfile
import tempfile
import tomllib
from functools import cache
from pathlib import Path

import facere as fac
import release

# Read by .github/actions/setup-fac/action.yml, so keep it on one line.
MINIMUM_FACERE = "0.3.0"

VERSION_FILE = "src/facere/_version.py"
DIST = "build/dist"

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


def _find_package_files() -> list[str]:
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


def _remove_dir(path: str) -> None:
    if os.path.exists(path):
        shutil.rmtree(path)


def _uv(*args: str, env: dict[str, str] | None = None) -> str:
    return fac.run("uv", *args, env=env)


def _uv_run(*args: str, env: dict[str, str] | None = None) -> str:
    return _uv("run", "--locked", *args, env=env)


@cache
def _fetch_latest_release(repo: str) -> tuple[int, ...]:
    url = f"https://github.com/{repo}"
    tags = fac.run("git", "ls-remote", "--tags", "--refs", url, quiet=True)
    return max(tuple(map(int, match.groups())) for match in RELEASE_TAG.finditer(tags))


def _bump_action_pins(text: str) -> str:
    """Move each `uses: owner/repo@v<pin>` to the newest release, keeping the pin's precision."""

    def bump(match: re.Match[str]) -> str:
        prefix, repo, pin = match.groups()
        latest = _fetch_latest_release(repo)[: pin.count(".") + 1]
        return f"{prefix}{repo}@v{'.'.join(map(str, latest))}"

    return ACTION_PIN.sub(bump, text)


def _fetch_current_branch() -> str:
    return fac.run("git", "branch", "--show-current", quiet=True).strip()


def _validate_wheel(directory: str, version: str) -> None:
    (wheel,) = glob.glob(f"{directory}/*.whl")
    reported = fac.run("uvx", "--isolated", "--from", wheel, "fac", "--version", quiet=True).strip()
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
    scratch_version_file = os.path.join(scratch, version_file)
    bumped = release.replace_version(fac.read_text(scratch_version_file), version)
    fac.write_text(scratch_version_file, bumped)
    fac.run(git, "commit", "--quiet", "--all", "--message", message)
    fac.run(git, "tag", "--annotate", "--message", message, tag)
    fac.run(git, "bundle", "create", "--quiet", os.path.abspath(RELEASE_BUNDLE), f"refs/tags/{tag}")
    _uv("build", scratch, "--out-dir", RELEASE_DIST)
    _validate_wheel(RELEASE_DIST, version)
    fac.write_text(RELEASE_VERSION, version)


fac.minimum_version(MINIMUM_FACERE)
_validate_released_facere()
PACKAGE_FILES = _find_package_files()


@fac.task(default=True)
def help_() -> None:
    """Print this help."""
    targets = {
        name.removesuffix("_"): inspect.getdoc(value) or ""
        for name, value in globals().items()
        if inspect.isfunction(value) and value.__module__ == __name__ and not name.startswith("_")
    }
    width = max(map(len, targets)) + 2
    lines = [
        "Usage: fac [TARGET]... [-- ARG]...",
        f"Develop Facere with a released Facere of at least {MINIMUM_FACERE}.",
        "With no TARGET, print this help. 'fac --help' shows Facere's own options.",
        "",
        "Targets:",
    ]
    for name, doc in targets.items():
        summary = doc.partition("\n")[0].replace("`", "'").removesuffix(".")
        lines.append(f"  {name:<{width}}{summary[:1].lower()}{summary[1:]}")
    print("\n".join(lines))


@fac.task
def example(project: fac.Input = "doc/examples/my-site") -> None:
    """Build `doc/examples/my-site` with Facere from source."""
    _uv_run("fac", "-C", project)


@fac.task
def lint() -> None:
    """Check formatting, lint, and types."""
    _uv_run("ruff", "check")
    _uv_run("ruff", "format", "--check")
    _uv_run("ty", "check")
    _uv_run("ty", "check", "--python-platform", "win32")


@fac.task
def test(args: fac.Args) -> None:
    """Lint, then run the tests, passing pytest the arguments after --, where --long adds those that take minutes."""
    lint()
    _uv_run("pytest", *args)


@fac.task
def ci(directory: fac.Input = DIST, version_file: fac.Input = VERSION_FILE) -> None:
    """Run what a pull request must pass: `test`, then a check of the wheel `dist` builds."""
    test(())
    _validate_wheel(directory, release.parse_version(fac.read_text(version_file)))


@fac.task
def test_sdist(directory: fac.Input = DIST) -> None:
    """Run the tests from the unpacked sdist `dist` builds, which holds what a downstream packager gets."""
    (sdist,) = glob.glob(f"{directory}/*.tar.gz")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        with tarfile.open(sdist) as archive:
            archive.extractall(scratch, filter="data")
        (unpacked,) = glob.glob(f"{scratch}/*")
        _uv("run", "--directory", unpacked, "pytest")


@fac.task
def coverage() -> None:
    """Run the tests serially under coverage, subprocesses included, and print the report."""
    data_dir = os.path.abspath("build/cov")
    _remove_dir(data_dir)
    # Absolute, since a test's commands run elsewhere. Safe path keeps the root, whose fac.py
    # would shadow a fixture's `import fac`, off the sys.path of `coverage run -m`.
    env = {"COVERAGE_FILE": os.path.join(data_dir, ".coverage"), "PYTHONSAFEPATH": "1"}
    _uv_run("coverage", "run", "-m", "pytest", "-q", "-n0", env=env)
    _uv_run("coverage", "combine", "-q", env=env)
    _uv_run("coverage", "report", "-m", env=env)


@fac.task
def format_() -> None:
    """Format, and fix what lint can."""
    _uv_run("ruff", "check", "--fix")
    _uv_run("ruff", "format")


@fac.task
def upgrade() -> None:
    """Upgrade the locked dependencies and the GitHub Actions pinned in `.github/`."""
    _uv("lock", "--upgrade")
    for path in glob.glob(ACTION_FILES, recursive=True):
        with open(path, encoding="utf-8", newline="") as file:
            text = file.read()
        bumped = _bump_action_pins(text)
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(bumped)


@fac.rule
def dist(files: list[fac.Input] = PACKAGE_FILES, directory: fac.Output = DIST) -> None:
    """Build the sdist and wheel into `build/dist/`."""
    _remove_dir(directory)
    _uv("build", "--out-dir", directory)


@fac.task
def build_release(args: fac.Args, version_file: str = VERSION_FILE) -> None:
    """Build a release of the type named after -- in a scratch clone, writing only under `build/`."""
    choice = release.parse_release_type(args)
    current = release.parse_version(fac.run("git", "show", f"HEAD:{version_file}", quiet=True))
    version = release.calc_next_version(current, choice)
    release.validate_release(version, choice, _fetch_current_branch())
    _remove_dir(RELEASE_DIR)
    os.makedirs(RELEASE_DIR)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        _build_release_in(scratch, version, version_file)


@fac.task
def push_release() -> None:
    """Push what `build_release` built: the branch and tag land together, or a moved branch rejects both."""
    tag = f"v{fac.read_text(RELEASE_VERSION)}"
    branch = _fetch_current_branch()
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
