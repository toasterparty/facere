"""Replaying a scenario file against the dependency engine.

A scenario is a text file: declarations of a graph and its saved traces, then a script of host calls and the events `poll` must return between them. Any implementation of the engine can replay the same files, since a line holds only names, keys, and digests. Tokens are separated by spaces, lists by commas, and a key is paired with its digest by a colon, so none of those appear in a name. Blank lines and lines starting with `#` are skipped.

Declarations come first:

    step NAME [digest=D] [in=KEY,...] [order=KEY,...] [out=KEY,...] [always] [pool=POOL]
    pool POOL SIZE
    keep_going
    trace NAME [digest=D] [in=KEY:D,...] [out=KEY:D,...] [found=KEY:D,...] [follows=KEY,...] [refused]
    duplicate KEY NAME NAME...
    cycle NAME:KEY NAME:KEY...

A step's digest, and its trace's, default to the step's name. `follows` is passed to load_trace, which otherwise takes the keys found, and `refused` expects it to refuse the trace. `duplicate` and `cycle` expect the graph to report them, and such a scenario has no script.

A script line is a host call:

    request NAME...
    give KEY:D,...
    finish NAME ok|failed|unsettled [found=KEY,...]
    forget NAME
    stop

or the event the next `poll` must return, written as format_event writes it:

    need KEY,... for NAME
    run NAME REASON [KEY]
    built NAME [in=KEY:D,...] [out=KEY:D,...] [found=KEY:D,...]
    built NAME unrecorded
    failed NAME input|output|found KEY
    idle
    done

An event line may end in ` -> ANSWER`, which answers it at once: the digest of each key in order after `need`, and the arguments of `finish` after `run`. The digest `-` stands for a key with nothing there.
"""

from pathlib import Path

from facere._engine import (
    Engine,
    Event,
    Failed,
    Graph,
    NeedDigests,
    Pause,
    Run,
    Status,
    Step,
    Trace,
)

_DECLARATIONS = ("step", "pool", "keep_going", "trace", "duplicate", "cycle")
_EVENTS = ("need", "run", "built", "failed", "idle", "done")


def replay(path: Path) -> None:
    """Replay the scenario at `path`, asserting each expectation it holds."""
    lines = [
        (number, line.split())
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip() and not line.startswith("#")
    ]
    declarations = [(number, tokens) for number, tokens in lines if tokens[0] in _DECLARATIONS]
    script = [(number, tokens) for number, tokens in lines if tokens[0] not in _DECLARATIONS]
    assert lines == [*declarations, *script], f"{path.name}: a declaration follows the script"
    names = [tokens[1] for _, tokens in declarations if tokens[0] == "step"]
    graph = Graph([_parse_step(tokens) for _, tokens in declarations if tokens[0] == "step"])
    expects_invalid = False
    for number, (kind, *args) in declarations:
        where = f"{path.name}:{number}"
        if kind == "duplicate":
            key, *steps = args
            assert [names[step] for step in graph.duplicates[key]] == steps, where
            expects_invalid = True
        elif kind == "cycle":
            assert graph.cycle is not None, where
            assert [f"{names[step]}:{key}" for step, key in graph.cycle] == args, where
            expects_invalid = True
    if expects_invalid:
        assert not script, f"{path.name}: a graph in error runs no script"
        return
    pool_sizes = {args[0]: int(args[1]) for _, (kind, *args) in declarations if kind == "pool"}
    keep_going = any(kind == "keep_going" for _, (kind, *_) in declarations)
    engine = Engine(graph, keep_going=keep_going, pool_sizes=pool_sizes)
    for number, (kind, *args) in declarations:
        if kind == "trace":
            name, fields, flags = _parse_fields(args)
            trace = Trace(
                fields.get("digest", name),
                _parse_pairs(fields.get("in", "")),
                _parse_pairs(fields.get("out", "")),
                _parse_pairs(fields.get("found", "")),
            )
            follows = _parse_list(fields, "follows") if "follows" in fields else None
            is_kept = engine.load_trace(names.index(name), trace, follows)
            assert is_kept == ("refused" not in flags), f"{path.name}:{number}"
    for number, tokens in script:
        expected, _, answer = " ".join(tokens).partition(" -> ")
        if tokens[0] in _EVENTS:
            event = engine.poll()
            actual = format_event(event, names)
            assert actual == expected, f"{path.name}:{number}: the engine returned `{actual}`"
            if answer:
                _answer(engine, event, answer.split())
        else:
            assert not answer, f"{path.name}:{number}: only an event takes an answer"
            _call(engine, names, tokens)


def format_event(event: Event, names: list[str]) -> str:
    """Return `event` as a scenario writes it, naming each step by `names`."""
    if isinstance(event, Pause):
        return event.name.lower()
    if isinstance(event, NeedDigests):
        return f"need {','.join(event.keys)} for {names[event.step]}"
    if isinstance(event, Run):
        key = "" if event.verdict.key is None else f" {event.verdict.key}"
        return f"run {names[event.step]} {event.verdict.reason.name.lower()}{key}"
    if isinstance(event, Failed):
        return f"failed {names[event.step]} {event.missing.name.lower()} {event.key}"
    if event.trace is None:
        return f"built {names[event.step]} unrecorded"
    fields = [
        f"{label}={','.join(f'{key}:{digest}' for key, digest in pairs)}"
        for label, pairs in (
            ("in", event.trace.inputs),
            ("out", event.trace.outputs),
            ("found", event.trace.found),
        )
        if pairs
    ]
    digest = [] if event.trace.digest == names[event.step] else [f"digest={event.trace.digest}"]
    return " ".join(["built", names[event.step], *digest, *fields])


def _parse_step(tokens: list[str]) -> Step:
    name, fields, flags = _parse_fields(tokens[1:])
    return Step(
        fields.get("digest", name),
        _parse_list(fields, "in"),
        _parse_list(fields, "order"),
        _parse_list(fields, "out"),
        "always" in flags,
        fields.get("pool"),
    )


def _parse_fields(tokens: list[str]) -> tuple[str, dict[str, str], list[str]]:
    """Return the name leading `tokens`, their `label=value` fields, and their bare flags."""
    name, *rest = tokens
    fields = dict(token.split("=", 1) for token in rest if "=" in token)
    return name, fields, [token for token in rest if "=" not in token]


def _parse_list(fields: dict[str, str], label: str) -> tuple[str, ...]:
    return tuple(fields[label].split(",")) if label in fields else ()


def _parse_pairs(text: str) -> tuple[tuple[str, str], ...]:
    pairs = (item.split(":", 1) for item in text.split(",") if item)
    return tuple((key, digest) for key, digest in pairs)


def _parse_finish(tokens: list[str]) -> tuple[Status, tuple[str, ...]]:
    status, fields, _ = _parse_fields(tokens)
    return Status[status.upper()], _parse_list(fields, "found")


def _parse_digest(text: str) -> str | None:
    return None if text == "-" else text


def _answer(engine: Engine, event: Event, answer: list[str]) -> None:
    if isinstance(event, NeedDigests):
        (digests,) = answer
        answers = map(_parse_digest, digests.split(","))
        engine.give_digests(dict(zip(event.keys, answers, strict=True)))
        return
    assert isinstance(event, Run)
    status, found = _parse_finish(answer)
    engine.finish(event.step, status, found)


def _call(engine: Engine, names: list[str], tokens: list[str]) -> None:
    call, *args = tokens
    if call == "request":
        engine.request([names.index(name) for name in args])
    elif call == "give":
        (pairs,) = args
        engine.give_digests({key: _parse_digest(digest) for key, digest in _parse_pairs(pairs)})
    elif call == "finish":
        name, *rest = args
        status, found = _parse_finish(rest)
        engine.finish(names.index(name), status, found)
    elif call == "forget":
        (name,) = args
        engine.forget_trace(names.index(name))
    else:
        assert tokens == ["stop"], f"unknown scenario line: {' '.join(tokens)}"
        engine.stop()
