"""What the dependency engine guarantees for every graph, checked against a model in which a key's digest is its content and a step writes a function of its own digest and of what it read."""

import itertools
import random
from collections.abc import Iterator
from typing import NamedTuple

import pytest

from facere._engine import (
    Built,
    Engine,
    Graph,
    NeedDigests,
    Pause,
    Reason,
    Run,
    Status,
    Step,
    Trace,
)

SOURCE = "x"


class Project(NamedTuple):
    """A graph with the inputs each step finds as it runs, and the state a build leaves: each key's content, each step's trace, and `memo`, what each step last read and wrote."""

    steps: list[Step]
    finds: list[tuple[str, ...]]
    contents: dict[str, str]
    traces: dict[int, Trace]
    memo: dict[int, tuple[str, list[str], list[str | None]]]

    def copy(self) -> "Project":
        return Project(
            list(self.steps), self.finds, dict(self.contents), dict(self.traces), dict(self.memo)
        )


def read(project: Project, index: int) -> list[str]:
    step = project.steps[index]
    return [project.contents[key] for key in (*step.inputs, *project.finds[index])]


def run(project: Project, index: int) -> None:
    """Write each output of the step as a function of its digest and all it reads, and remember both."""
    step = project.steps[index]
    seen = read(project, index)
    for key in step.outputs:
        project.contents[key] = f"{key}({step.digest};{','.join(seen)})"
    project.memo[index] = (step.digest, seen, [project.contents[key] for key in step.outputs])


def find_closure(project: Project, targets: list[int]) -> list[int]:
    """Return `targets` with every step that writes a key they read or follow, in declaration order."""
    producers = {key: index for index, step in enumerate(project.steps) for key in step.outputs}
    closure: set[int] = set()
    stack = list(targets)
    while stack:
        index = stack.pop()
        if index in closure:
            continue
        closure.add(index)
        step = project.steps[index]
        stack.extend(producers[key] for key in (*step.inputs, *step.order_only) if key in producers)
    return sorted(closure)


def find_stale(project: Project, targets: list[int]) -> list[int]:
    """Return the steps a build of `targets` must run, by brute force on a copy: each step, after those before it, that last read or wrote anything other than what is there now."""
    scratch = project.copy()
    stale = []
    for index in find_closure(scratch, targets):
        step = scratch.steps[index]
        outputs = [scratch.contents.get(key) for key in step.outputs]
        if scratch.memo.get(index) != (step.digest, read(scratch, index), outputs):
            stale.append(index)
            run(scratch, index)
    return stale


def build(
    project: Project, targets: list[int], pool_sizes: dict[str, int] | None = None
) -> list[int]:
    """Build `targets` with the engine on one worker, and return the steps it ran, in order."""
    engine = Engine(Graph(project.steps), pool_sizes=pool_sizes)
    for index, trace in project.traces.items():
        engine.load_trace(index, trace)
    engine.request(targets)
    ran = []
    while (event := engine.poll()) is not Pause.DONE:
        if isinstance(event, NeedDigests):
            engine.give_digests({key: project.contents.get(key) for key in event.keys})
        elif isinstance(event, Run):
            ran.append(event.step)
            project.traces.pop(event.step, None)
            run(project, event.step)
            engine.finish(event.step, Status.OK, project.finds[event.step])
        else:
            assert isinstance(event, Built) and event.trace is not None, event
            project.traces[event.step] = event.trace
    return ran


def iter_projects(step_count: int) -> Iterator[Project]:
    """Yield every project of `step_count` steps, each writing one key, where a step treats the source, and each key an earlier step writes, in each way it can: not at all, as an input, as an input found while running, or, for a written key, as one only ordered after."""
    roles_by_step = [
        itertools.product("-if", *["-iof"] * index, repeat=1) for index in range(step_count)
    ]
    for roles in itertools.product(*roles_by_step):
        steps = []
        finds = []
        for index, step_roles in enumerate(roles):
            keys = [SOURCE, *(f"out{earlier}" for earlier in range(index))]
            by_role = {
                role: tuple(key for key, held in zip(keys, step_roles, strict=True) if held == role)
                for role in "iof"
            }
            order_only = (*by_role["o"], *(key for key in by_role["f"] if key != SOURCE))
            steps.append(Step(f"d{index}", by_role["i"], order_only, (f"out{index}",)))
            finds.append(by_role["f"])
        yield Project(steps, finds, {SOURCE: "x1"}, {}, {})


def iter_edits(project: Project) -> Iterator[Project]:
    """Yield a copy of the built `project` after each single edit: to the source, and to each step's digest, output, and trace."""
    edited = project.copy()
    edited.contents[SOURCE] = "x2"
    yield edited
    for index, step in enumerate(project.steps):
        edited = project.copy()
        edited.steps[index] = step._replace(digest="edited")
        yield edited
        for content in ("tampered", None):
            edited = project.copy()
            if content is None:
                del edited.contents[step.outputs[0]]
            else:
                edited.contents[step.outputs[0]] = content
            yield edited
        edited = project.copy()
        del edited.traces[index]
        del edited.memo[index]
        yield edited


def build_fresh(project: Project, targets: list[int]) -> dict[str, str]:
    """Return what each key `targets` reach holds once every step they reach has run, starting from the source alone."""
    fresh = Project(project.steps, project.finds, {SOURCE: project.contents[SOURCE]}, {}, {})
    closure = find_closure(fresh, targets)
    for index in closure:
        run(fresh, index)
    return {key: fresh.contents[key] for index in closure for key in fresh.steps[index].outputs}


def check_every_project(step_count: int) -> None:
    """Build every project of `step_count` steps, then after each single edit build its last step, then everything, then everything again."""
    everything = list(range(step_count))
    for project in iter_projects(step_count):
        assert build(project, everything) == everything
        for edited in iter_edits(project):
            for targets in ([step_count - 1], everything):
                stale = find_stale(edited, targets)

                assert build(edited, targets) == stale

                fresh = build_fresh(edited, targets)
                assert {key: edited.contents[key] for key in fresh} == fresh
            assert build(edited, everything) == []


def test_every_project_of_one_or_two_steps_runs_exactly_its_stale_steps_and_ends_as_a_fresh_build() -> (
    None
):
    check_every_project(1)
    check_every_project(2)


@pytest.mark.long
def test_every_project_of_three_steps_runs_exactly_its_stale_steps_and_ends_as_a_fresh_build() -> (
    None
):
    check_every_project(3)


class Worker(NamedTuple):
    """A simulated worker thread: the event it polled and has yet to answer, if any."""

    held: list[NeedDigests | Run]


def build_interleaved(
    project: Project, targets: list[int], pool_sizes: dict[str, int], rng: random.Random
) -> list[int]:
    """Build `targets` on four simulated workers that poll and answer in an order `rng` picks, asserting the engine's contract at each event, and return the steps run."""
    graph = Graph(project.steps)
    engine = Engine(graph, pool_sizes=pool_sizes)
    for index, trace in project.traces.items():
        engine.load_trace(index, trace)
    engine.request(targets)
    workers = [Worker([]) for _ in range(4)]
    done: set[int] = set()
    ran: list[int] = []
    built: set[int] = set()
    asked: set[str] = set()
    while len(done) < len(workers):
        number = rng.choice([number for number in range(len(workers)) if number not in done])
        held = workers[number].held
        if held:
            event = held.pop()
            if isinstance(event, NeedDigests):
                asked.difference_update(event.keys)
                engine.give_digests({key: project.contents.get(key) for key in event.keys})
            else:
                run(project, event.step)
                engine.finish(event.step, Status.OK, project.finds[event.step])
            continue
        event = engine.poll()
        if event is Pause.DONE:
            assert not any(worker.held for worker in workers), "done while an event is out"
            done.add(number)
        elif event is Pause.IDLE:
            assert any(worker.held for worker in workers), "idle with nothing to wait for"
        elif isinstance(event, NeedDigests):
            assert asked.isdisjoint(event.keys), f"one of {event.keys} asked for twice at once"
            asked.update(event.keys)
            held.append(event)
        elif isinstance(event, Run):
            assert event.step not in ran, f"step {event.step} ran twice"
            current = {
                step
                for step, verdict in engine.verdicts.items()
                if verdict.reason is Reason.CURRENT
            }
            assert (built | current).issuperset(graph.upstream[event.step]), "ran before upstream"
            running = [worker.held[0] for worker in workers if worker.held]
            pool = project.steps[event.step].pool
            in_pool = [
                held
                for held in running
                if isinstance(held, Run) and graph.steps[held.step].pool == pool
            ]
            assert pool is None or len(in_pool) < pool_sizes[pool], f"pool {pool} overfilled"
            ran.append(event.step)
            project.traces.pop(event.step, None)
            held.append(event)
        else:
            assert isinstance(event, Built) and event.trace is not None, event
            project.traces[event.step] = event.trace
            built.add(event.step)
    return ran


def build_random_project(rng: random.Random) -> Project:
    """Return a project of twelve steps, each reading up to three of the source and the keys before it, half of them in a pool."""
    steps = []
    for index in range(12):
        keys = [SOURCE, *(f"out{earlier}" for earlier in range(index))]
        inputs = tuple(rng.sample(keys, rng.randint(0, min(3, len(keys)))))
        pool = rng.choice([None, "narrow"])
        steps.append(Step(f"d{index}", inputs, (), (f"out{index}",), pool=pool))
    return Project(steps, [()] * len(steps), {SOURCE: "x1"}, {}, {})


def test_workers_polling_in_any_order_run_the_steps_one_worker_does() -> None:
    rng = random.Random(0)
    pool_sizes = {"narrow": 2}
    for _ in range(200):
        project = build_random_project(rng)
        everything = list(range(len(project.steps)))
        assert sorted(build_interleaved(project, everything, pool_sizes, rng)) == everything
        edited = next(itertools.islice(iter_edits(project), rng.randrange(40), None))
        serial = edited.copy()
        expected = build(serial, everything, pool_sizes)

        assert sorted(build_interleaved(edited, everything, pool_sizes, rng)) == expected
        assert edited.contents == serial.contents
