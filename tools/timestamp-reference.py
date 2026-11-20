#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click"]
# ///
"""Measure, on the file system holding DIRECTORY, how well each reference time tells a file changed after it from one changed before.

A reference is read, then a file is changed: a miss is a change whose ctime, or mtime with `--mtime`, reads earlier than the reference taken before it. A file is changed, then a reference is read: a false flag is a change that reads at or after the reference taken after it. The probe reference is the mtime of a file rewritten in PROBE_DIRECTORY, DIRECTORY unless given, so the two can lie on different file systems.
"""

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import click

NS_PER_MS = 1_000_000
# Python's time module names no coarse clock, so this is Linux's id for it from <linux/time.h>.
LINUX_CLOCK_REALTIME_COARSE = 5


def read_precise_clock(_: Path) -> int:
    return time.time_ns()


def read_coarse_clock(_: Path) -> int:
    return time.clock_gettime_ns(LINUX_CLOCK_REALTIME_COARSE)


def read_probe(probe: Path) -> int:
    with open(probe, "wb"):
        pass
    return os.stat(probe).st_mtime_ns


def change_by_rename(target: Path) -> None:
    staged = target.with_suffix(".staged")
    staged.write_bytes(b"x")
    os.replace(staged, target)


def change_in_place(target: Path) -> None:
    target.write_bytes(b"x")


@click.command()
@click.argument("directory", type=click.Path(file_okay=False, path_type=Path))
@click.option("--probe-directory", type=click.Path(file_okay=False, path_type=Path))
@click.option("--samples", default=20000, show_default=True)
@click.option(
    "--mtime", "use_mtime", is_flag=True, help="Read each change's mtime, as Windows needs."
)
def main(directory: Path, probe_directory: Path | None, samples: int, use_mtime: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    probe = (probe_directory or directory) / "reference.probe"
    probe.parent.mkdir(parents=True, exist_ok=True)
    target = directory / "changed.txt"
    references: dict[str, Callable[[Path], int]] = {"time.time_ns": read_precise_clock}
    if sys.platform == "linux":
        references["CLOCK_REALTIME_COARSE"] = read_coarse_clock
    references["probe file"] = read_probe
    changes = {"rename": change_by_rename, "write in place": change_in_place}

    def read_change_time() -> int:
        info = os.stat(target)
        return info.st_mtime_ns if use_mtime else info.st_ctime_ns

    click.echo(
        f"{'reference':<22} {'change':<15} {'missed':>8} {'worst lag':>10} {'flagged':>8} {'read cost':>10}"
    )
    for reference_name, read_reference in references.items():
        for change_name, change in changes.items():
            missed = 0
            worst_lag_ns = 0
            flagged = 0
            cost_ns = 0
            for _ in range(samples):
                started_ns = time.perf_counter_ns()
                reference_ns = read_reference(probe)
                cost_ns += time.perf_counter_ns() - started_ns
                change(target)
                lag_ns = reference_ns - read_change_time()
                missed += lag_ns > 0
                worst_lag_ns = max(worst_lag_ns, lag_ns)
                change(target)
                changed_ns = read_change_time()
                flagged += changed_ns >= read_reference(probe)
            click.echo(
                f"{reference_name:<22} {change_name:<15} {missed / samples:>8.1%} "
                f"{worst_lag_ns / NS_PER_MS:>8.2f}ms {flagged / samples:>8.1%} "
                f"{cost_ns / samples / 1000:>8.1f}us"
            )


if __name__ == "__main__":
    main()
