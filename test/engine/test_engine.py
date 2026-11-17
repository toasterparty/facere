"""The dependency engine's module stands alone, and its staleness decision is a pure function of a step, its trace, and the digests known."""

import ast
from pathlib import Path

from facere import _engine
from facere._engine import Reason, Step, Trace, Verdict, decide

STEP = Step("d1", inputs=("main.c",), outputs=("main.o",))
TRACE = Trace("d1", (("main.c", "c1"),), (("main.o", "o1"),), (("a.h", "h1"),))


def test_engine_imports_only_the_standard_library() -> None:
    tree = ast.parse(Path(_engine.__file__).read_text(encoding="utf-8"))

    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]

    assert sorted(ast.unparse(node) for node in imports) == [
        "from collections import deque",
        "from collections.abc import Iterable, Mapping, Sequence",
        "from typing import NamedTuple",
        "import enum",
        "import heapq",
    ]


def test_decide_asks_for_the_inputs_then_for_what_the_trace_found_and_the_outputs() -> None:
    assert decide(STEP, TRACE, {}) == ["main.c"]
    assert decide(STEP, TRACE, {"main.c": "c1"}) == ["a.h", "main.o"]


def test_decide_finds_a_step_current_once_every_digest_matches_its_trace() -> None:
    digests = {"main.c": "c1", "a.h": "h1", "main.o": "o1"}

    assert decide(STEP, TRACE, digests) == Verdict(Reason.CURRENT)


def test_decide_reads_no_output_of_a_step_whose_input_changed() -> None:
    assert decide(STEP, TRACE, {"main.c": "c2"}) == Verdict(Reason.INPUT_CHANGED, "main.c")


def test_decide_names_a_found_input_that_is_gone_as_changed() -> None:
    digests = {"main.c": "c1", "a.h": None, "main.o": "o1"}

    assert decide(STEP, TRACE, digests) == Verdict(Reason.INPUT_CHANGED, "a.h")
