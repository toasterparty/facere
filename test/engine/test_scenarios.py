"""Each file in `scenarios/` pins one behavior of the dependency engine, stated in its first line, as a transcript any implementation of the engine can replay."""

from pathlib import Path

import pytest

from .scenario import replay

SCENARIOS = sorted((Path(__file__).parent / "scenarios").glob("*.txt"))


@pytest.mark.parametrize("path", SCENARIOS, ids=[path.stem for path in SCENARIOS])
def test_engine_replays_the_scenario(path: Path) -> None:
    replay(path)
