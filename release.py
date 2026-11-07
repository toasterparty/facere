"""The rules deciding which version a release becomes and whether it may happen.

Free of Facere and git, so `test/test_release.py` covers them directly.
"""

import re

__all__ = [
    "CHOICES",
    "calc_next_version",
    "parse_release_type",
    "parse_version",
    "replace_version",
    "validate_release",
]

CHOICES = ("Major", "Minor", "Patch")

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_VERSION_LINE = re.compile(r'^VERSION = "(.+)"$', re.MULTILINE)
_HOTFIX_PREFIX = "hotfix/"


def parse_version(text: str) -> str:
    """Return the version the version file's text holds, raising ValueError if it holds none."""
    match = _VERSION_LINE.search(text)
    if match is None:
        raise ValueError(f"no line matching {_VERSION_LINE.pattern} in:\n{text}")
    return str(match[1])


def replace_version(text: str, version: str) -> str:
    """Return the version file's text with its version changed to `version`."""
    return _VERSION_LINE.sub(f'VERSION = "{version}"', text)


def parse_release_type(args: tuple[str, ...]) -> str:
    """Return the one argument given after `--`, raising ValueError on any other count."""
    if len(args) != 1:
        raise ValueError(f"expected one of {', '.join(CHOICES)} after --, not {list(args)}")
    return args[0]


def calc_next_version(current: str, choice: str) -> str:
    """Return the version that releasing `choice` makes from `current`, raising ValueError if either is malformed."""
    if choice not in CHOICES:
        raise ValueError(f"release type {choice!r} is not one of {', '.join(CHOICES)}")
    match = _VERSION.fullmatch(current)
    if match is None:
        raise ValueError(f"version {current!r} is not X.Y.Z")
    numbers = [int(number) for number in match.groups()]
    raised = CHOICES.index(choice)
    bumped = [*numbers[:raised], numbers[raised] + 1, *[0] * (len(numbers) - raised - 1)]
    return ".".join(map(str, bumped))


def validate_release(version: str, choice: str, branch: str) -> None:
    is_hotfix = branch.startswith(_HOTFIX_PREFIX)
    if branch != "main" and not is_hotfix:
        raise ValueError(f"releases run from main or {_HOTFIX_PREFIX}*, not {branch!r}")
    if is_hotfix and choice != "Patch":
        raise ValueError(f"branch {branch!r} releases only Patch, not {choice!r}")
    if int(version.partition(".")[0]) >= 1:
        raise ValueError(
            f"release {version} is blocked until 1.0 is due: delete this check from release.py"
        )
