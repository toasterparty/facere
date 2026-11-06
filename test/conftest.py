import shutil
from pathlib import Path

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "project(name): copy the project NAME, in the directory named after the test module, into the root",
    )
    if config.option.basetemp is None:
        basetemp = config.rootpath / "build" / "test" / "tmp"
        basetemp.parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = basetemp


@pytest.fixture
def root(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Return the test's root: `tmp_path`, holding a copy of the project the test's `project` marker names, if any."""
    marker = request.node.get_closest_marker("project")
    if marker is not None:
        (name,) = marker.args
        shutil.copytree(
            request.path.with_suffix("") / name,
            tmp_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "build"),
        )
    return tmp_path
