"""The line closing an invocation: how long it took, what ran, and what was already current."""

from dataclasses import dataclass

_MS_PER_SECOND = 1000
_TENTHS_PER_SECOND = 10
_TENTHS_PER_MINUTE = 600
_MINUTES_PER_HOUR = 60


@dataclass(slots=True)
class Summary:
    tasks_run: int = 0
    rules_run: int = 0
    outputs_current: int = 0
    stopped: str | None = None


def format_summary(summary: Summary, elapsed_s: float, *, is_interrupted: bool) -> str:
    """Return the closing line, leaving out each section with nothing to report, under a line naming the definition an interrupt stopped.

    Sections are separated by `. `.
    """
    elapsed = _format_elapsed(elapsed_s)
    lead = f"Interrupted after {elapsed}" if is_interrupted else f"Finished in {elapsed}"
    sections = [lead]
    ran = [
        _format_count(count, noun)
        for count, noun in ((summary.tasks_run, "task"), (summary.rules_run, "rule"))
        if count
    ]
    if ran:
        sections.append(f"Executed {' and '.join(ran)}")
    elif not is_interrupted:
        sections.append("No work to do")
    if summary.outputs_current:
        sections.append(f"{_format_count(summary.outputs_current, 'output')} up to date")
    line = ". ".join(sections) + "."
    if summary.stopped is None:
        return line
    return f"Stopped {summary.stopped}\n{line}"


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
