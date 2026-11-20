#!/usr/bin/env python3
"""Time a no-op `fac` invocation on a generated project shaped like the budget's C project, using this tree's Facere.

Run it as `fac bench`, which runs it under the repo's environment and passes it the arguments after `--`. The project holds RULES compiles, each reading its own source and reporting REPORTS of HEADERS headers through fac.add_inputs, and one link over every object. It builds once, then times RUNS no-op invocations, each a fresh `python -m facere` process, and prints the median and the fastest. No compiler is involved, so the times are Facere's own.

`--base REF` also times REF's `src/` on a twin project beside `--dir`, alternating the two trees run by run so drift in the machine's load hits both alike.
"""

import argparse
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DIR = TOP_DIR / "build" / "noop-benchmark" / "project"

FAC_PY = """\
import facere as fac

RULES = {rules}
HEADERS = {headers}
REPORTS = {reports}

COMPILES = [
    {{
        "source": f"src/s{{index:04d}}.c",
        "obj": fac.out(f"obj/s{{index:04d}}.o"),
        "headers": [f"include/h{{(index * 7 + step * 13) % HEADERS:04d}}.h" for step in range(REPORTS)],
    }}
    for index in range(RULES)
]


@fac.rule(each=COMPILES)
def compile_(source: fac.Input, obj: fac.Output, headers: list[str]):
    fac.add_inputs(headers)
    fac.write_text(obj, fac.read_text(source))


@fac.rule(default=True)
def link(objects: list[fac.Input] = [row["obj"] for row in COMPILES], app: fac.Output = fac.out("app")):
    fac.write_text(app, str(len(objects)))
"""


def _generate(root: Path, rules: int, headers: int, reports: int) -> None:
    shutil.rmtree(root, ignore_errors=True)
    (root / "src").mkdir(parents=True)
    (root / "include").mkdir()
    for index in range(headers):
        (root / "include" / f"h{index:04d}.h").write_text(f"header {index}\n")
    for index in range(rules):
        (root / "src" / f"s{index:04d}.c").write_text(f"source {index}\n")
    (root / "fac.py").write_text(FAC_PY.format(rules=rules, headers=headers, reports=reports))


def _run_fac(root: Path, src: Path | None = None) -> float:
    """Return the seconds one `fac` process takes in `root`, which must succeed, importing Facere from `src` where given."""
    env = os.environ if src is None else {**os.environ, "PYTHONPATH": str(src)}
    start_s = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "facere", "-q"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_s = time.perf_counter() - start_s
    if result.returncode != 0:
        sys.exit(f"fac failed in {root}:\n{result.stderr}")
    return elapsed_s


def _export_src(ref: str, dest: Path) -> Path:
    archive = subprocess.run(
        ["git", "-C", str(TOP_DIR), "archive", ref, "src"], capture_output=True, check=False
    )
    if archive.returncode != 0:
        sys.exit(f"git archive {ref} failed:\n{archive.stderr.decode()}")
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return dest / "src"


def _benchmark(trees: dict[str, tuple[Path, Path | None]], args: argparse.Namespace) -> None:
    """Build each tree's project, then time `args.runs` no-ops per tree, alternating trees run by run."""
    for label, (root, src) in trees.items():
        _generate(root, args.rules, args.headers, args.reports)
        print(f"{label}: build {_run_fac(root, src) * 1000:.0f} ms")
    time.sleep(args.settle_s)
    for root, src in trees.values():
        _run_fac(root, src)
    times_ms: dict[str, list[float]] = {label: [] for label in trees}
    for _ in range(args.runs):
        for label, (root, src) in trees.items():
            times_ms[label].append(_run_fac(root, src) * 1000)
    for label, runs_ms in times_ms.items():
        print(
            f"{label}: no-op median {statistics.median(runs_ms):.0f} ms, fastest {min(runs_ms):.0f} ms"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dir", type=Path, default=DEFAULT_DIR, help="where to generate the project"
    )
    parser.add_argument("--rules", type=int, default=1000)
    parser.add_argument("--headers", type=int, default=5000)
    parser.add_argument("--reports", type=int, default=30)
    parser.add_argument("--runs", type=int, default=15)
    parser.add_argument(
        "--settle-s", type=float, default=2.5, help="wait after the build, so no entry is racy"
    )
    parser.add_argument("--base", help="a git ref whose src/ to time against the working tree's")
    args = parser.parse_args()
    if args.base is None:
        _benchmark({"tree": (args.dir, None)}, args)
        return
    with tempfile.TemporaryDirectory() as tmp:
        base_src = _export_src(args.base, Path(tmp))
        base_dir = args.dir.with_name(f"{args.dir.name}-base")
        _benchmark({"tree": (args.dir, None), args.base: (base_dir, base_src)}, args)


if __name__ == "__main__":
    main()
