import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "release.py")
assert _SPEC is not None and _SPEC.loader is not None
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)


def test_patch_raises_the_last_part() -> None:
    assert release.calc_next_version("0.2.0", "Patch") == "0.2.1"


def test_minor_zeroes_the_patch() -> None:
    assert release.calc_next_version("0.2.3", "Minor") == "0.3.0"


def test_major_zeroes_the_parts_after_it() -> None:
    assert release.calc_next_version("1.2.3", "Major") == "2.0.0"


def test_unknown_choice_is_rejected() -> None:
    with pytest.raises(ValueError, match="is not one of"):
        release.calc_next_version("0.2.0", "minor")


def test_version_outside_the_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="is not X.Y.Z"):
        release.calc_next_version("0.2.0b1", "Patch")


def test_main_and_hotfix_branches_may_release() -> None:
    release.validate_release("0.3.0", "Minor", "main")
    release.validate_release("0.2.1", "Patch", "hotfix/v0.2")


def test_other_branches_may_not_release() -> None:
    with pytest.raises(ValueError, match="releases run from main"):
        release.validate_release("0.3.0", "Minor", "feature/x")


def test_detached_checkout_may_not_release() -> None:
    with pytest.raises(ValueError, match="releases run from main"):
        release.validate_release("0.3.0", "Minor", "")


def test_hotfix_branch_releases_only_a_patch() -> None:
    with pytest.raises(ValueError, match="releases only Patch"):
        release.validate_release("0.3.0", "Minor", "hotfix/v0.2")


def test_one_point_zero_is_blocked() -> None:
    with pytest.raises(ValueError, match="is blocked"):
        release.validate_release("1.0.0", "Major", "main")
