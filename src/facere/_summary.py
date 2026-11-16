"""The line closing an invocation: how it ended, how long it took, what ran, and what was already current."""

import enum
from dataclasses import dataclass, field

from facere._diagnostics import Diagnostic

_MS_PER_SECOND = 1000
_TENTHS_PER_SECOND = 10
_TENTHS_PER_MINUTE = 600
_MINUTES_PER_HOUR = 60


class Outcome(enum.Enum):
    """How an invocation ended. Each value is the exit status."""

    FINISHED = 0
    FAILED = 1
    UNSTARTED = 2
    LOCK_TIMEOUT = 3
    CRASHED = 4
    INTERRUPTED = 130
    STOPPED = 143


# The first word of the closing line, which a caller may parse.
_LEADS = {
    Outcome.FINISHED: "Finished in",
    Outcome.FAILED: "Failed after",
    Outcome.UNSTARTED: "Failed after",
    Outcome.LOCK_TIMEOUT: "Failed after",
    Outcome.CRASHED: "Failed after",
    Outcome.INTERRUPTED: "Interrupted after",
    Outcome.STOPPED: "Stopped after",
}


@dataclass(slots=True)
class Summary:
    """What an invocation did.

    `failed` counts the rules and tasks that failed. `ended` holds one note per recipe that an interrupt or a stop ended, and `unsettled` one warning per rule that an input changing during its recipe left stale twice in a row.
    """

    tasks_run: int = 0
    rules_run: int = 0
    outputs_current: int = 0
    failed: int = 0
    ended: list[Diagnostic] = field(default_factory=list)
    unsettled: list[Diagnostic] = field(default_factory=list)


def format_summary(summary: Summary, elapsed_s: float, outcome: Outcome) -> str:
    """Return the closing line, leaving out each section with nothing to report.

    Sections are separated by `. `.
    """
    sections = [f"{_LEADS[outcome]} {_format_elapsed(elapsed_s)}"]
    ran = [
        _format_count(count, noun)
        for count, noun in ((summary.tasks_run, "task"), (summary.rules_run, "rule"))
        if count
    ]
    if ran:
        sections.append(f"Executed {' and '.join(ran)}")
    elif outcome is Outcome.FINISHED:
        sections.append("No work to do")
    if summary.outputs_current:
        sections.append(f"{_format_count(summary.outputs_current, 'output')} up to date")
    return ". ".join(sections) + "."


def _format_count(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _format_elapsed(elapsed_s: float) -> str:
    total_tenths = round(elapsed_s * _TENTHS_PER_SECOND)
    if total_tenths < _TENTHS_PER_SECOND:
        return f"{round(elapsed_s * _MS_PER_SECOND)}ms"
    minutes, tenths = divmod(total_tenths, _TENTHS_PER_MINUTE)
    hours, minutes = divmod(minutes, _MINUTES_PER_HOUR)
    parts = []
    if hours:
        parts.append(f"{hours}hr")
    if hours or minutes:
        parts.append(f"{minutes}min")
    parts.append(f"{tenths / _TENTHS_PER_SECOND:.1f}s")
    return " ".join(parts)
