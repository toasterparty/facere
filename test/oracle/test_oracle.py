"""After any sequence of edits to a generated project, an incremental build leaves the outputs a build into a fresh output directory writes, executes exactly the rules the edits made stale, and leaves a second build nothing to execute."""

import enum
import os
import posixpath
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
from hypothesis import HealthCheck, seed, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)

import facere

from .family import (
    ENVS,
    MODULES,
    PARTS,
    TEXT_PATHS,
    TEXTS,
    VALUES,
    File,
    Project,
    Row,
    projects,
    subsets,
)

_OUT = "build"
_FRESH_OUT = "../fresh"
_SETTINGS = settings(
    max_examples=6,
    stateful_step_count=8,
    deadline=None,
    database=None,
    suppress_health_check=list(HealthCheck),
)
_LONG_SETTINGS = settings(_SETTINGS, max_examples=100, stateful_step_count=20, derandomize=False)
_LONG_SHARDS = 8
_MTIME_STEP_NS = 1_000_000_000


class _Refresh(enum.Enum):
    """A way to change what a stat shows of a file while keeping its content."""

    TOUCH = enum.auto()
    REWRITE = enum.auto()
    REPLACE = enum.auto()


class _Damage(enum.Enum):
    DELETE = enum.auto()
    OVERWRITE = enum.auto()


class _Record(NamedTuple):
    """What the row's rule depended on when a build last brought it up to date."""

    facts: dict[str, object]
    include_names: frozenset[str]


class _IncrementalBuilds(RuleBasedStateMachine):
    """Each rule edits the project or its outputs, and the invariant then builds and checks.

    `records` mirrors what Facere's state should hold, so comparing a record with what its row depends on now names the rows a build must execute, and why.
    """

    def __init__(self, work: Path, capfd: pytest.CaptureFixture[str]) -> None:
        super().__init__()
        shutil.rmtree(work, ignore_errors=True)
        self.root = work / "project"
        self.fresh_dir = self.root / _FRESH_OUT
        self.capfd = capfd
        self.project: Project
        self.keeps_mtimes = False
        self.edits_per_build = 1
        self.builds_one_first = False
        self.files: dict[str, File] = {}
        self.fresh: dict[str, File] | None = None
        self.records: dict[str, _Record] = {}
        self.damaged: set[str] = set()
        self.listing: frozenset[str] = frozenset()
        self.declared: frozenset[str] | None = None
        self.known_outputs: set[str] = set()
        self.unbuilt_edits = 0
        self.builds = 0
        self.log: list[str] = []

    @initialize(
        project=projects(),
        keeps_mtimes=st.booleans(),
        edits_per_build=st.integers(1, 2),
        builds_one_first=st.booleans(),
    )
    def start(
        self, project: Project, keeps_mtimes: bool, edits_per_build: int, builds_one_first: bool
    ) -> None:
        """Write the project. With `keeps_mtimes`, each later edit restores its file's mtime, as `cp -p` and archive extraction do. A build follows every `edits_per_build` edits, and with `builds_one_first` it builds one output before the rest."""
        self.project = project
        self.keeps_mtimes = keeps_mtimes
        self.edits_per_build = edits_per_build
        self.builds_one_first = builds_one_first
        (self.root / "notes").mkdir(parents=True)
        self._apply("start")
        self.unbuilt_edits = edits_per_build

    @rule(path=st.sampled_from(TEXT_PATHS), text=st.sampled_from(TEXTS))
    def write_file(self, path: str, text: str) -> None:
        """Edit a source, a header, or a note, or add it."""
        self.project.write(path, text)
        self._apply(f"write {path} as {text!r}")

    @precondition(lambda self: self.project.find_removable())
    @rule(data=st.data())
    def remove_file(self, data: st.DataObject) -> None:
        """Remove a source, a note, or a header no include needs, a generated one included."""
        path = data.draw(st.sampled_from(self.project.find_removable()))
        self.project.remove(path)
        self._apply(f"remove {path}")

    @rule(data=st.data())
    def include_headers(self, data: st.DataObject) -> None:
        name = data.draw(st.sampled_from(sorted(self.project.sources)))
        includes = data.draw(subsets(self.project.find_resolvable()))
        self.project.sources[name] = self.project.sources[name]._replace(includes=includes)
        self._apply(f"include {includes} from src/{name}.txt")

    @rule(data=st.data(), part=st.sampled_from(PARTS))
    def edit_code(self, data: st.DataObject, part: str) -> None:
        """Edit a recipe or a helper: what it returns, its syntax alone, its comments alone, or its name."""
        codes = self.project.find_codes()
        code = codes[data.draw(st.sampled_from(sorted(codes)))]
        setattr(code, part, getattr(code, part) + 1)
        self._apply(f"edit the {part} of {code.key}")

    @rule(data=st.data(), value=st.sampled_from(VALUES))
    def change_value(self, data: st.DataObject, value: object) -> None:
        """Change a constant, an argument, a default, or a closure variable, or generate a header."""
        setters = self.project.find_setters()
        name = data.draw(st.sampled_from(sorted(setters)))
        setters[name](value)
        self._apply(f"set {name} to {value!r}")

    @rule(module=st.sampled_from(MODULES))
    def comment_module(self, module: str) -> None:
        self.project.module_layouts[module] += 1
        self._apply(f"add a comment line to the top of {module}.py")

    @rule(env=st.sampled_from(ENVS))
    def change_env(self, env: dict[str, str | None]) -> None:
        self.project.env = env
        self._apply(f"call fac.env with {env}")

    @rule(is_swapped=st.booleans())
    def place_outputs(self, is_swapped: bool) -> None:
        self.project.is_swapped = is_swapped
        self._apply(f"declare the outputs of link {'swapped' if is_swapped else 'in order'}")

    @precondition(lambda _: sys.platform != "win32")
    @rule(data=st.data())
    def toggle_executable(self, data: st.DataObject) -> None:
        path = data.draw(st.sampled_from(sorted(self.files)))
        self.project.executables ^= {path}
        self._apply(f"toggle the executable bit of {path}")

    @rule(data=st.data(), how=st.sampled_from(_Refresh))
    def refresh_file(self, data: st.DataObject, how: _Refresh) -> None:
        """Change the timestamps or the inode of a project file or an output, and keep its content, so nothing is stale."""
        paths = [*self.files, *(f"{_OUT}/{output}" for output in self._find_outputs())]
        path = data.draw(st.sampled_from(sorted(paths)))
        self._refresh(self.root / path, how)
        self._count_edit(f"{how.name.lower()} {path}")

    @precondition(lambda self: self._find_outputs())
    @rule(data=st.data(), how=st.sampled_from(_Damage))
    def damage_output(self, data: st.DataObject, how: _Damage) -> None:
        outputs = self._find_outputs()
        output = data.draw(st.sampled_from(sorted(outputs)))
        if how is _Damage.DELETE:
            (self.root / _OUT / output).unlink()
        else:
            (self.root / _OUT / output).write_bytes(b"damaged")
        self.damaged.add(outputs[output])
        self._count_edit(f"{how.name.lower()} {_OUT}/{output}")

    @precondition(lambda self: (self.root / _OUT / ".fac").exists())
    @rule(is_state_alone=st.booleans())
    def delete_output_directory(self, is_state_alone: bool) -> None:
        """Delete the output directory, or Facere's state alone, which keeps the outputs and forgets every record."""
        directory = self.root / _OUT / ".fac" if is_state_alone else self.root / _OUT
        shutil.rmtree(directory)
        self.records.clear()
        self.listing = frozenset()
        self.declared = None
        self._count_edit(f"delete {directory.relative_to(self.root).as_posix()}")

    @invariant()
    def incremental_build_matches_a_fresh_build(self) -> None:
        if self.unbuilt_edits < self.edits_per_build:
            return
        rows = self.project.calc_rows()
        fresh = self._build_fresh()
        self.builds += 1
        if self.builds_one_first:
            self._build(rows, sorted(rows)[self.builds % len(rows)])
        self._build(rows, None)
        built = _read_outputs(self.root / _OUT)
        self.known_outputs.update(fresh)
        orphans = self.known_outputs - fresh.keys()
        current = {path: file for path, file in built.items() if path not in orphans}
        assert current == fresh, self._describe("the incremental build differs from a fresh one")
        again = self._run_fac()
        assert again == set(), self._describe(f"a second build executed {sorted(again)}")
        self.unbuilt_edits = 0

    def _build(self, rows: dict[str, Row], row_id: str | None) -> None:
        """Build the output of the row `row_id`, or every output when None, and check that exactly the stale rows it reaches executed."""
        fresh = self._build_fresh()
        self._forget_records(rows)
        reached = sorted(rows) if row_id is None else sorted({row_id, *rows[row_id].needs})
        facts = {
            reached_id: {
                **rows[reached_id].facts,
                **{f"built {path}": fresh[path] for path in rows[reached_id].built},
            }
            for reached_id in reached
        }
        stale = {
            reached_id: reasons
            for reached_id in reached
            if (reasons := self._find_stale_reasons(reached_id, facts[reached_id]))
        }
        target = [] if row_id is None else [f"{_OUT}/{rows[row_id].target}"]
        executed = self._run_fac(*target)
        assert executed == stale.keys(), self._describe(
            f"fac {' '.join(target)} executed {sorted(executed)}, where these were stale: {stale}"
        )
        for reached_id in reached:
            self.records[reached_id] = _Record(facts[reached_id], rows[reached_id].include_names)
        self.damaged.difference_update(reached)

    def _forget_records(self, rows: dict[str, Row]) -> None:
        """Forget what an invocation forgets before it builds: the record of each rule no longer declared, and of each whose recipe reported a file name that a file or an output new since the last invocation has."""
        listing = frozenset(path for path in self.files if not path.startswith("../"))
        declared = frozenset(output for row in rows.values() for output in row.outputs)
        new = (listing - self.listing) | (declared - (self.declared or declared))
        new_names = {posixpath.basename(path) for path in new}
        self.records = {
            row_id: record
            for row_id, record in self.records.items()
            if row_id in rows and record.include_names.isdisjoint(new_names)
        }
        self.listing = listing
        self.declared = declared

    def _find_stale_reasons(self, row_id: str, facts: dict[str, object]) -> list[str]:
        record = self.records.get(row_id)
        if record is None:
            return ["no record"]
        changed = [
            key
            for key in sorted(facts.keys() | record.facts.keys())
            if facts.get(key) != record.facts.get(key)
        ]
        return [*changed, *(["damaged output"] if row_id in self.damaged else [])]

    def _build_fresh(self) -> dict[str, File]:
        """Return the outputs a build into a fresh output directory writes from the project as it stands."""
        if self.fresh is None:
            shutil.rmtree(self.fresh_dir, ignore_errors=True)
            self._run_fac("--out", _FRESH_OUT)
            self.fresh = _read_outputs(self.fresh_dir)
        return self.fresh

    def _run_fac(self, *args: str) -> set[str]:
        """Run fac in the project, which must succeed, and return the ids of the rows that executed."""
        self.capfd.readouterr()
        status = facere.main(["-C", str(self.root), *args])
        captured = self.capfd.readouterr()
        assert status == 0, self._describe(f"fac {' '.join(args)} failed:\n{captured.err}")
        return {
            line.removeprefix("ran ").removeprefix(f"{_OUT}/")
            for line in captured.out.splitlines()
            if line.startswith("ran ")
        }

    def _apply(self, edit: str) -> None:
        """Write the files the project now renders to, where they differ from those on disk."""
        files = self.project.render()
        if files == self.files:
            return
        for path in self.files.keys() - files.keys():
            (self.root / path).unlink()
        for path, file in files.items():
            if self.files.get(path) != file:
                self._write(self.root / path, file)
        self.files = files
        self.fresh = None
        self._count_edit(edit)

    def _write(self, path: Path, file: File) -> None:
        before = path.stat() if self.keeps_mtimes and path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file.content)
        path.chmod(0o755 if file.is_executable else 0o644)
        if before is not None:
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    def _refresh(self, path: Path, how: _Refresh) -> None:
        match how:
            case _Refresh.TOUCH:
                before = path.stat()
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + _MTIME_STEP_NS))
            case _Refresh.REWRITE:
                path.write_bytes(path.read_bytes())
            case _Refresh.REPLACE:
                copy = path.with_name(f"{path.name}.copy")
                shutil.copy(path, copy)
                os.replace(copy, path)

    def _count_edit(self, edit: str) -> None:
        self.log.append(edit)
        self.unbuilt_edits += 1

    def _find_outputs(self) -> dict[str, str]:
        """Return the id of the row of each declared output a build has written, by the output's path."""
        return {
            output: row_id
            for row_id, row in self.project.calc_rows().items()
            for output in row.outputs
            if (self.root / _OUT / output).is_file()
        }

    def _describe(self, failure: str) -> str:
        edits = "\n".join(f"    {edit}" for edit in self.log)
        return f"{failure}\nproject: {self.root}\nedits:\n{edits}"


def _read_outputs(out_dir: Path) -> dict[str, File]:
    """Return every file under `out_dir` by its path relative to it, Facere's state aside."""
    return {
        path.relative_to(out_dir).as_posix(): File(path.read_bytes(), os.access(path, os.X_OK))
        for path in sorted(out_dir.rglob("*"))
        if path.is_file() and path.relative_to(out_dir).parts[0] != ".fac"
    }


def _run_machine(
    work: Path,
    capfd: pytest.CaptureFixture[str],
    machine_settings: settings,
    fixed_seed: int | None,
) -> None:
    """Run the state machine in `work`, under `fixed_seed`, or under a new seed on every run when None."""

    class Machine(_IncrementalBuilds):
        def __init__(self) -> None:
            super().__init__(work, capfd)

    factory = Machine if fixed_seed is None else seed(fixed_seed)(Machine)
    run_state_machine_as_test(factory, settings=machine_settings)


def test_incremental_build_matches_a_fresh_build_after_any_edits(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _run_machine(tmp_path / "example", capfd, _SETTINGS, fixed_seed=0)


@pytest.mark.long
@pytest.mark.parametrize("shard", range(_LONG_SHARDS))
def test_incremental_build_matches_a_fresh_build_over_a_long_run(
    shard: int, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """Each shard explores under a new seed on every run, and a failure prints the seed that repeats it."""
    _run_machine(tmp_path / "example", capfd, _LONG_SETTINGS, fixed_seed=None)
