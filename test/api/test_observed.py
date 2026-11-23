"""A cycle of a watch, which `fac --watch` runs as `fac --watched`, records in the state what it observed, which the watch polls for a change."""

from pathlib import Path

import pytest

from facere import _state
from facere._observed import ABSENT, calc_watch_key

from ..helpers import Fac, edit

_STATE = "build/.fac/state.db"


def _load(root: Path, *targets: str) -> _state.Observation:
    loaded = _state.load_observation(str(root / _STATE), calc_watch_key(list(targets)))
    assert loaded is not None
    return loaded[1]


@pytest.mark.project("kinds")
def test_a_cycle_records_what_collection_loaded_read_and_listed_what_it_hashed_and_its_tasks_inputs(
    root: Path, fac: Fac
) -> None:
    assert fac("--watched", "app", "serve").status == 0

    observation = _load(root, "app", "serve")
    assert sorted(observation.files) == [
        "build/app",
        "fac.py",
        "greeting.txt",
        "lib.py",
        "notes.txt",
        "site/index.html",
        "src/a.c",
        "src/b.c",
    ]
    assert sorted(observation.dirs) == ["site", "src"]
    assert observation.outputs == {"build/app"}


@pytest.mark.project("kinds")
def test_an_invocation_outside_a_watch_records_nothing(root: Path, fac: Fac) -> None:
    assert fac("app").status == 0

    assert _state.load_observation(str(root / _STATE), calc_watch_key(["app"])) is None


@pytest.mark.project("kinds")
def test_each_watch_keeps_its_own_record_on_one_output_directory(root: Path, fac: Fac) -> None:
    fac("--watched", "app")
    fac("--watched", "serve")

    assert "notes.txt" not in _load(root, "app").files
    assert "notes.txt" in _load(root, "serve").files


@pytest.mark.project("kinds")
def test_a_failed_collection_keeps_what_the_last_collected_cycle_observed_with_what_it_tried_to_load(
    root: Path, fac: Fac
) -> None:
    fac("--watched", "app")
    collected = _load(root, "app")
    edit(root / "lib.py", "def join(texts):", "def join(texts)")

    assert fac("--watched", "app").status == 2

    observation = _load(root, "app")
    assert observation.files.keys() == collected.files.keys()
    assert observation.files["lib.py"] != collected.files["lib.py"]
    assert observation.files["fac.py"] == collected.files["fac.py"]


@pytest.mark.project("kinds")
def test_a_missing_input_that_fails_collection_is_recorded_as_absent(root: Path, fac: Fac) -> None:
    (root / "notes.txt").unlink()

    assert fac("--watched", "serve").status == 2

    assert _load(root, "serve").files["notes.txt"] == ABSENT


@pytest.mark.project("failing")
def test_the_outputs_of_a_failed_rule_are_left_out(root: Path, fac: Fac) -> None:
    assert fac("--watched", "-k", "half", "whole").status == 1

    observation = _load(root, "half", "whole")
    assert sorted(observation.files) == ["build/whole.txt", "fac.py", "source.txt"]
    assert observation.outputs == {"build/whole.txt"}
