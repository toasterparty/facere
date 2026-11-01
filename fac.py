"""Develop Facere with its latest release: `uvx facere <task>`."""

import glob
import os
import shutil
import subprocess

import facere as fac

DIST = "build/dist"


def _load_uv_env() -> dict[str, str]:
    """Read project.env, letting a variable already set in the environment win, as tools/uv.sh does."""
    path = os.path.join(os.path.dirname(__file__), "project.env")
    with open(path, encoding="utf-8") as file:
        pairs = [line.strip().split("=", 1) for line in file if line.strip()]
    return {key: os.environ.get(key, value) for key, value in pairs}


UV_ENV = _load_uv_env()


def _uv(*args: str) -> str:
    return fac.run("uv", *args, env=UV_ENV)


def _uv_run(*args: str) -> str:
    return _uv("run", "--locked", *args)


def _lint() -> None:
    _uv_run("ruff", "check")
    _uv_run("ruff", "format", "--check")
    _uv_run("ty", "check")


@fac.task(default=True)
def run(example: fac.Input = "examples/hello") -> None:
    _uv_run("fac", "-C", example)


@fac.task
def lint() -> None:
    _lint()


@fac.task
def test() -> None:
    _lint()
    _uv_run("pytest")


@fac.task
def format_() -> None:
    _uv_run("ruff", "check", "--fix")
    _uv_run("ruff", "format")


@fac.task
def upgrade() -> None:
    if not os.environ.get("CI"):
        try:
            _uv("self", "update", "-q")
        except subprocess.CalledProcessError:
            print("fac: uv self update failed, as it does when a package manager installed uv")
    _uv("lock", "--upgrade")


@fac.task
def publish() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    _uv("build", "--out-dir", DIST)
    _uv("publish", *sorted(glob.glob(f"{DIST}/*")))
