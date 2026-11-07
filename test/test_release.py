import pytest

from facere._version import VERSION

from .helpers import REPO, load_module

release = load_module(REPO / "release.py")


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


def test_version_is_read_from_the_package_version_file() -> None:
    text = (REPO / "src" / "facere" / "_version.py").read_text(encoding="utf-8")

    assert release.parse_version(text) == VERSION


def test_text_without_a_version_line_is_rejected() -> None:
    with pytest.raises(ValueError, match="no line matching"):
        release.parse_version('VERSION = 1\nOTHER_VERSION = "1.2.3"\n')


def test_replacing_the_version_leaves_other_lines_alone() -> None:
    text = 'OTHER = "x"\nVERSION = "0.1.0"\nLAST = 2\n'

    assert release.replace_version(text, "0.2.0") == 'OTHER = "x"\nVERSION = "0.2.0"\nLAST = 2\n'


def test_release_type_is_the_one_argument_after_the_separator() -> None:
    assert release.parse_release_type(("Minor",)) == "Minor"


@pytest.mark.parametrize("args", [(), ("Minor", "Patch")])
def test_release_type_arguments_other_than_one_are_rejected(args: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="expected one of Major, Minor, Patch after --"):
        release.parse_release_type(args)
