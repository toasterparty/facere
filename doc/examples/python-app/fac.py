import datetime
import glob
import os
import shutil
import sys
import tomllib

import facere as fac

import hello_world

fac.minimum_version("1.0")

with open("pyproject.toml", "rb") as file:
    PROJECT = tomllib.load(file)["project"]
NAME, VERSION = PROJECT["name"], PROJECT["version"]
MODULE = NAME.replace("-", "_")
COMPANY = "Example Organization"
SHOW_CONSOLE = True
PLATFORM = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")

CACHE = {"PYTHONPYCACHEPREFIX": fac.out("pycache")}
DEV = fac.uv.Project(env=CACHE)
RELEASE = fac.uv.Project(venv=fac.out("release/.venv"), editable=False, env=CACHE)
PACKAGE = fac.sources(f"{MODULE}/**") + DEV.inputs + ["setup.cfg", "README.md", "LICENSE"]
PYPI = fac.out("pypi")
ARCHIVE = fac.out(f"{NAME}-v{VERSION}-{PLATFORM}" + (".zip" if PLATFORM == "windows" else ".tar.gz"))

NUITKA = [
    "--mode=standalone",
    "--deployment",
    "--python-flag=-m",
    "--assume-yes-for-downloads",
    f"--output-dir={fac.out('dist')}",
    f"--output-filename={NAME}" + (".exe" if PLATFORM == "windows" else ""),
    f"--include-distribution-metadata={NAME}",
    f"--include-package-data={MODULE}",
    "--enable-plugin=tk-inter",
]
if PLATFORM == "windows":
    NUITKA += [
        "--msvc=latest",
        "--windows-console-mode=" + ("attach" if SHOW_CONSOLE else "disable"),
        f"--windows-icon-from-ico={MODULE}/assets/icon.ico",
        f"--company-name={COMPANY}",
        f"--product-name={hello_world.PRODUCT_NAME}",
        f"--file-description={PROJECT['description']}",
        f"--copyright=Copyright {datetime.date.today().year} {COMPANY}",
        f"--file-version={VERSION}",
        f"--product-version={VERSION}",
    ]


@fac.task
def lint():
    """Check formatting, lint, and types."""
    DEV.run("ruff", "check")
    DEV.run("ruff", "format", "--check")
    DEV.run("ty", "check")


@fac.task
def test():
    """Lint, then run the unit tests."""
    lint()
    DEV.run("pytest")


@fac.task(default=True)
def run():
    """Run the app from source."""
    fac.give_lock()
    DEV.run(NAME, inherit=True)


@fac.task
def format_():
    """Fix lint and format the sources in place."""
    DEV.run("ruff", "check", "--fix")
    DEV.run("ruff", "format")


@fac.task
def upgrade():
    """Upgrade the locked dependencies."""
    fac.run("uv", "lock", "--upgrade")


@fac.rule
def release(
    sources: list[fac.Input] = PACKAGE,
    archive: fac.Output = ARCHIVE,
):
    """Build the standalone executable and archive it."""
    RELEASE.run("python", "-m", "nuitka", NUITKA, MODULE)
    fac.write_archive(archive, fac.out(f"dist/{MODULE}.dist"), top=NAME)


@fac.rule(clear=True)
def pypi(sources: list[fac.Input] = PACKAGE, out: fac.Output = PYPI):
    """Build the sdist and wheel."""
    fac.run("uv", "build", "--out-dir", out)


@fac.task
def publish(packages: fac.Input = PYPI):
    """Publish the sdist and wheel to PyPI through trusted publishing, from CI."""
    trusted = ["GITHUB_ACTIONS", "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    fac.run("uv", "publish", sorted(glob.glob(f"{packages}/*")), inherit=trusted)


@fac.task
def clean():
    """Delete the output directory. The development venv at the root stays."""
    if os.path.exists(fac.out()):
        shutil.rmtree(fac.out())
