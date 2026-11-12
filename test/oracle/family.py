"""A family of small generated Facere projects: the files one renders to, and what each of its rules depends on.

Four rule functions chain. `generate` writes one header per row. `compile` expands the headers each source includes, searching directories in order as a compiler does and reporting what it finds. `link` joins the objects with a directory of notes into two outputs, and `stamp` runs a tool over the first. Their recipes reach helper functions spread over fac.py and two shared modules, each function returning its text with a tag that shows everything its fingerprint should hold, so a stale output differs from a fresh one in its bytes.
"""

from __future__ import annotations

import copy
import enum
import functools
import posixpath
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple, TypeVar

from hypothesis import strategies as st

MODULES = ("base", "lib", "fac")
"""The project's Python files, each of which may use those before it."""
CONSTANTS = ("K0", "K1")
RECIPES = ("generate", "compile", "link")
PARTS = ("salt", "noise", "layout", "renames")
SEARCH = ("local", "include")
"""Where `compile` looks for a header first, in order."""
SDK = "../sdk"
"""Where it looks last, after the generated headers: Facere lists no file outside the root, so a new one there must shadow nothing."""
HEADER_DIRECTORIES = (*SEARCH, SDK)
HEADER_NAMES = ("x.h", "y.h")
SOURCE_NAMES = ("a", "b", "c")
NOTE_NAMES = ("n.md", "x.h")
TEXT_PATHS = (
    *(f"src/{name}.txt" for name in SOURCE_NAMES),
    *(f"{directory}/{name}" for directory in HEADER_DIRECTORIES for name in HEADER_NAMES),
    *(f"notes/{name}" for name in NOTE_NAMES),
)
"""Every file an edit may write: the sources, the written headers, and the notes."""
TEXTS = ("one", "two", "six")
INITIAL_TEXT = "nil"
"""What every file holds at first, apart from TEXTS so that no first write leaves a file as it was."""
ENVS: tuple[dict[str, str | None], ...] = (
    {"ORACLE_MARK": "a"},
    {"ORACLE_MARK": "b"},
    {"ORACLE_MARK": None},
    {},
)

_T = TypeVar("_T")


class Gap(enum.Enum):
    """Something Facere gets wrong today, which the family leaves out while OPEN_GAPS holds its member."""

    # A set and a frozenset of equal items hash alike, so swapping one for the other executes nothing.
    SET_KINDS = enum.auto()
    # A function a constant holds, as in a dict of handlers, hashes by name alone, where the design hashes its module.
    HELD_FUNCTIONS = enum.auto()
    # A constant a class body binds to an attribute stays out of the fingerprint.
    CLASS_CONSTANTS = enum.auto()


OPEN_GAPS = frozenset(Gap)
"""The gaps not yet fixed. Remove a member to generate what it left out, then delete it with its guards once the oracle passes."""

VALUES: tuple[object, ...] = (
    *(1, True, 0, False, 1.0, "1", b"1", None, (1,), [1], {1}, {"k": 1}),
    *(() if Gap.SET_KINDS in OPEN_GAPS else (frozenset({1}),)),
)

_PRELUDES = {
    "base": "import functools\n",
    "lib": "import functools\n\nimport base\n",
    "fac": "import functools\nimport os\nimport posixpath\nimport sys\n\nimport base\nimport lib\n\nimport facere as fac\n",
}
_TRACED = """
def traced(fn):
    @functools.wraps(fn)
    def wrapper(text):
        return fn(text)

    return wrapper
"""
_FAC_HELPERS = f"""
SEARCH = {list(SEARCH)!r}
SDK = {SDK!r}
SOURCES = fac.sources("src/*.txt")
OBJECTS = [fac.out(source, ".o") for source in SOURCES]


def expand(source, generated):
    lines = []
    for line in fac.read_text(source).splitlines():
        name = line.removeprefix("#include ")
        if name == line:
            lines.append(line)
            continue
        candidates = [f"{{directory}}/{{name}}" for directory in SEARCH]
        candidates += [path for path in generated if posixpath.basename(path) == name]
        candidates.append(f"{{SDK}}/{{name}}")
        found = next(path for path in candidates if os.path.isfile(path))
        fac.add_inputs([found])
        lines.append(fac.read_text(found))
    return "\\n".join(lines)


def join(objects, notes):
    paths = [*objects, *(f"{{notes}}/{{name}}" for name in sorted(os.listdir(notes)))]
    return "\\n".join(fac.read_text(path) for path in paths)
"""
_STAMP = """
@fac.rule
def stamp(
    tool: fac.Input = "tool.py",
    source: fac.Input = fac.out("app.txt"),
    target: fac.Output = fac.out("stamp.txt"),
) -> None:
    fac.run(sys.executable, "-I", "-S", tool, source, target)
    print("ran stamp")
"""
_TOOL = """import os
import sys

SALT = {salt!r}

with open(sys.argv[1], "rb") as file:
    text = file.read()
tag = f"[tool {{SALT!r}} {{os.environ.get('ORACLE_MARK')}}]"
with open(sys.argv[2], "wb") as file:
    file.write(text + tag.encode())
"""


class Form(enum.Enum):
    """How a helper is defined, one member per way a fingerprint reaches code."""

    PLAIN = enum.auto()
    # Behind a decorator the project defines, whose closure holds the function.
    TRACED = enum.auto()
    # Behind a standard library decorator, which keeps the function in `__wrapped__`.
    WRAPPED = enum.auto()
    # Binding its module's K1 as a parameter default.
    DEFAULT = enum.auto()
    # Returned by a factory, with a value in its closure.
    CLOSURE = enum.auto()
    # A method of a class that inherits the method it ends with.
    METHOD = enum.auto()
    # Called through a dict that a constant holds.
    HELD = enum.auto()


_FORMS = [form for form in Form if form is not Form.HELD or Gap.HELD_FUNCTIONS not in OPEN_GAPS]
_K1_BINDING_FORMS = (
    (Form.DEFAULT,) if Gap.CLASS_CONSTANTS in OPEN_GAPS else (Form.DEFAULT, Form.METHOD)
)


class File(NamedTuple):
    content: bytes
    is_executable: bool


class Source(NamedTuple):
    """A file `compile` reads: a line of text, then an `#include` line per header name."""

    text: str
    includes: tuple[str, ...] = ()
    value: object = 0


class Row(NamedTuple):
    """One rule.

    `target` and `outputs` are relative to the output directory, as is `built`, the outputs of other rules whose content the rule depends on. `needs` names the rows built before it. `facts` holds everything else that makes it stale when it changes, by what a failure should call it. `include_names` holds the file name of each header its recipe reports.
    """

    target: str
    outputs: tuple[str, ...]
    needs: frozenset[str]
    facts: dict[str, object]
    built: tuple[str, ...]
    include_names: frozenset[str]


@dataclass(slots=True)
class Code:
    """A generated function, a recipe or a helper.

    It passes its text through each of `calls`, helpers by key, then adds a tag showing `salt` and each of the `reads`, constants by module and name. `noise` changes its syntax tree alone, and `layout` only its comments, docstring, and blank lines. `bound` is the value a CLOSURE helper's closure holds, or the one a METHOD helper's inherited method shows.
    """

    key: str
    module: str
    calls: tuple[str, ...] = ()
    reads: tuple[tuple[str, str], ...] = ()
    form: Form = Form.PLAIN
    bound: object = 0
    salt: int = 0
    noise: int = 0
    layout: int = 0
    renames: int = 0

    @property
    def name(self) -> str:
        return f"{self.key}_{self.renames}" if self.renames else self.key


@dataclass(slots=True)
class Project:
    """One member of the family, which the oracle's edits change in place.

    `headers` maps each header a person wrote, as a path relative to the root in one of the HEADER_DIRECTORIES, to its text, and `generated` each header name `generate` writes to its row's value. `executables` holds the rendered paths whose executable bit is set.
    """

    helpers: dict[str, Code]
    recipes: dict[str, Code]
    sources: dict[str, Source]
    headers: dict[str, str]
    generated: dict[str, object]
    notes: dict[str, str]
    constants: dict[tuple[str, str], object] = field(
        default_factory=lambda: {(module, name): 0 for module in MODULES for name in CONSTANTS}
    )
    module_layouts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MODULES, 0))
    env: dict[str, str | None] = field(default_factory=dict)
    flag: object = 0
    level: object = 0
    is_swapped: bool = False
    tool_salt: object = 0
    executables: set[str] = field(default_factory=set)

    def render(self) -> dict[str, File]:
        """Return the project's files by path relative to the root, with `/`."""
        texts = {
            **{f"{module}.py": self._render_module(module) for module in MODULES},
            "tool.py": _TOOL.format(salt=self.tool_salt),
            **{f"src/{name}.txt": _render_source(source) for name, source in self.sources.items()},
            **self.headers,
            **{f"notes/{name}": text for name, text in self.notes.items()},
        }
        return {path: File(text.encode(), path in self.executables) for path, text in texts.items()}

    def calc_rows(self) -> dict[str, Row]:
        """Return each rule by the id its recipe prints after `ran`, less the output directory."""
        files = self.render()
        env = repr(self.env)
        generated = {f"gen/{name}": value for name, value in sorted(self.generated.items())}
        objects = tuple(f"src/{name}.o" for name in sorted(self.sources))
        rows = {
            path: Row(
                target=path,
                outputs=(path,),
                needs=frozenset(),
                facts={**self._calc_code_facts("generate"), "env": env, "value": repr(value)},
                built=(),
                include_names=frozenset(),
            )
            for path, value in generated.items()
        }
        for name, source in sorted(self.sources.items()):
            includes = [
                path
                for header in source.includes
                if (path := self.find_include(header)) is not None
            ]
            read = [f"src/{name}.txt", *(path for path in includes if path not in generated)]
            rows[f"src/{name}.o"] = Row(
                target=f"src/{name}.o",
                outputs=(f"src/{name}.o",),
                needs=frozenset(generated),
                facts={
                    **self._calc_code_facts("compile"),
                    **{f"file {path}": files[path] for path in read},
                    "env": env,
                    "value": repr(source.value),
                    "flag": repr(self.flag),
                    "order-only": tuple(generated),
                },
                built=tuple(path for path in includes if path in generated),
                include_names=frozenset(source.includes),
            )
        first, second = self._calc_link_outputs()
        rows["link"] = Row(
            target=first,
            outputs=(first, second),
            needs=frozenset(rows),
            facts={
                **self._calc_code_facts("link"),
                **{f"file notes/{name}": files[f"notes/{name}"] for name in self.notes},
                "env": env,
                "level": repr(self.level),
                "inputs": objects,
                "outputs": (first, second),
            },
            built=objects,
            include_names=frozenset(),
        )
        rows["stamp"] = Row(
            target="stamp.txt",
            outputs=("stamp.txt",),
            needs=frozenset(rows),
            facts={"file tool.py": files["tool.py"], "env": env},
            built=("app.txt",),
            include_names=frozenset(),
        )
        return rows

    def find_include(self, name: str) -> str | None:
        """Return the header `#include NAME` resolves to: a path relative to the root, or to the output directory for a generated one."""
        for directory in SEARCH:
            if f"{directory}/{name}" in self.headers:
                return f"{directory}/{name}"
        if name in self.generated:
            return f"gen/{name}"
        return f"{SDK}/{name}" if f"{SDK}/{name}" in self.headers else None

    def find_resolvable(self) -> list[str]:
        """Return the header names an `#include` resolves."""
        return [name for name in HEADER_NAMES if self.find_include(name) is not None]

    def find_codes(self) -> dict[str, Code]:
        return {**self.recipes, **self.helpers}

    def find_setters(self) -> dict[str, Callable[[object], None]]:
        """Return a function setting each value an edit may change, by what a failure should call it: a constant, a value a rule's parameter receives, the one a helper binds, or the one a generated header or the tool shows."""

        def set_row_value(name: str, value: object) -> None:
            self.sources[name] = self.sources[name]._replace(value=value)

        return {
            **{
                f"{module}.{name}": functools.partial(self.constants.__setitem__, (module, name))
                for module, name in self.constants
            },
            **{
                f"the value of src/{name}.txt": functools.partial(set_row_value, name)
                for name in self.sources
            },
            **{
                f"the value of gen/{name}": functools.partial(self.generated.__setitem__, name)
                for name in HEADER_NAMES
            },
            **{
                f"the value {key} binds": functools.partial(setattr, helper, "bound")
                for key, helper in self.helpers.items()
                if helper.form in (Form.CLOSURE, Form.METHOD)
            },
            **{
                name: functools.partial(setattr, self, name)
                for name in ("flag", "level", "tool_salt")
            },
        }

    def find_removable(self) -> list[str]:
        """Return the files and generated headers an edit may remove: all but the last source, and each header every source's includes resolve without."""
        included = {name for source in self.sources.values() for name in source.includes}
        providers = [*self.headers, *(f"gen/{name}" for name in self.generated)]
        headers = [
            path
            for path in providers
            if posixpath.basename(path) not in included
            or any(
                other != path and posixpath.basename(other) == posixpath.basename(path)
                for other in providers
            )
        ]
        sources = [f"src/{name}.txt" for name in self.sources] if len(self.sources) > 1 else []
        return sorted([*headers, *sources, *(f"notes/{name}" for name in self.notes)])

    def write(self, path: str, text: str) -> None:
        """Set the text of `path`, one of TEXT_PATHS, adding the file where the project lacks it."""
        directory, name = posixpath.split(path)
        if directory == "src":
            name = posixpath.splitext(name)[0]
            self.sources[name] = self.sources.get(name, Source(text))._replace(text=text)
        elif directory == "notes":
            self.notes[name] = text
        else:
            self.headers[path] = text

    def remove(self, path: str) -> None:
        """Remove `path`, one of those find_removable returns."""
        directory, name = posixpath.split(path)
        if directory == "src":
            del self.sources[posixpath.splitext(name)[0]]
        elif directory == "notes":
            del self.notes[name]
        elif directory == "gen":
            del self.generated[name]
        else:
            del self.headers[path]

    def _calc_code_facts(self, recipe: str) -> dict[str, object]:
        """Return what the code `recipe` reaches adds to a fingerprint: each function's syntax, and each constant one reads."""
        facts: dict[str, object] = {}
        pending = [self.recipes[recipe]]
        while pending:
            code = pending.pop()
            shown = repr(code.bound) if code.form in (Form.CLOSURE, Form.METHOD) else None
            facts[f"code {code.key}"] = (code.name, code.salt, code.noise, code.form, shown)
            defaults = [(code.module, "K1")] if code.form in _K1_BINDING_FORMS else []
            if code.form is Form.HELD:
                facts[f"syntax of {code.module}.py"] = self._render_syntax(code.module)
            for module, name in (*code.reads, *defaults):
                facts[f"constant {module}.{name}"] = repr(self.constants[module, name])
            pending.extend(self.helpers[key] for key in code.calls)
        return facts

    def _calc_link_outputs(self) -> tuple[str, str]:
        return ("app.map", "app.txt") if self.is_swapped else ("app.txt", "app.map")

    def _render_syntax(self, module: str) -> str:
        """Return `module` as it renders without the comments, docstrings, and blank lines an edit to a layout changes, which is what its syntax tree holds."""
        bare = copy.deepcopy(self)
        bare.module_layouts = dict.fromkeys(MODULES, 0)
        for code in bare.find_codes().values():
            code.layout = 0
        return bare._render_module(module)

    def _render_module(self, module: str) -> str:
        lines = [f"# layout {index}" for index in range(self.module_layouts[module])]
        lines += [_PRELUDES[module], _TRACED]
        lines += [f"{name} = {self.constants[module, name]!r}" for name in CONSTANTS]
        if module == "fac":
            if self.env:
                lines.append(f"fac.env(**{self.env!r})")
            lines.append(_FAC_HELPERS)
        for helper in self.helpers.values():
            if helper.module == module:
                lines += ["", *self._render_helper(helper)]
        if module == "fac":
            lines += [*self._render_rules(), _STAMP]
        return "\n".join(lines) + "\n"

    def _render_helper(self, helper: Code) -> list[str]:
        name = helper.name
        match helper.form:
            case Form.PLAIN:
                header, shown = f"def {name}(text):", ()
            case Form.TRACED:
                header, shown = f"@traced\ndef {name}(text):", ()
            case Form.WRAPPED:
                header, shown = f"@functools.singledispatch\ndef {name}(text):", ()
            case Form.DEFAULT:
                header, shown = f"def {name}(text, mark=K1):", ("mark",)
            case Form.CLOSURE:
                inner = self._render_function(helper, f"def {name}(text):", "text", ("mark",))
                return [
                    f"def make_{name}(mark):",
                    *_indent([*inner, "    return text", f"return {name}"]),
                    f"{name} = make_{name}({helper.bound!r})",
                ]
            case Form.HELD:
                held = self._render_function(helper, f"def {name}_held(text):", "text", ())
                return [
                    *held,
                    "    return text",
                    f'{name}_table = {{"go": {name}_held}}',
                    f"def {name}(text):",
                    f'    return {name}_table["go"](text)',
                ]
            case Form.METHOD:
                method = self._render_function(helper, "def apply(self, text):", "text", ())
                binds_constant = Form.METHOD in _K1_BINDING_FORMS
                return [
                    f"class {name}_base:",
                    *(["    mark = K1"] if binds_constant else []),
                    "    def finish(self, text):",
                    f"        bound = {helper.bound!r}",
                    *(["        bound = (bound, self.mark)"] if binds_constant else []),
                    f'        return f"{{text}}[{helper.key} base {{bound!r}}]"',
                    f"class {name}({name}_base):",
                    *_indent([*method, "    return self.finish(text)"]),
                ]
        return [*self._render_function(helper, header, "text", shown), "    return text"]

    def _render_function(
        self, code: Code, header: str, argument: str, shown: tuple[str, ...]
    ) -> list[str]:
        """Return `code` as a function leaving its tagged result in `text`, where `argument` is the text it starts from and the tag also shows the expressions `shown`."""
        for key in code.calls:
            helper = self.helpers[key]
            callee = _calc_reference(code.module, helper.module, helper.name)
            call = f"{callee}().apply" if helper.form is Form.METHOD else callee
            argument = f"{call}({argument})"
        reads = [_calc_reference(code.module, module, name) for module, name in code.reads]
        tag = " ".join(
            [code.key, str(code.salt), *(f"{{{item!s}!r}}" for item in (*reads, *shown))]
        )
        body = [f"text = {argument}", f'text = f"{{text}}[{tag}]"']
        if code.noise:
            body.insert(0, f"_ = {code.noise}")
        if code.layout >= 2:
            body.insert(0, f"# layout {code.layout}")
        if code.layout % 2:
            body.insert(0, f'"""Layout {code.layout}."""')
        return [*[""] * (code.layout % 3), *header.split("\n"), *_indent(body)]

    def _render_rules(self) -> list[str]:
        generate, compile_, link = (self.recipes[name] for name in RECIPES)
        generated = [f'fac.out("gen/{name}")' for name in sorted(self.generated)]
        generate_rows = [
            f'{{"target": {target}, "value": {self.generated[name]!r}}}'
            for name, target in zip(sorted(self.generated), generated, strict=True)
        ]
        values = {f"src/{name}.txt": source.value for name, source in self.sources.items()}
        compile_row = (
            '{"source": source, "target": fac.out(source, ".o"), "value": ROW_VALUES[source]}'
        )
        first, second = self._calc_link_outputs()
        return [
            f"GENERATED = [{', '.join(generated)}]",
            f"ROW_VALUES = {values!r}",
            f"@fac.rule(each=[{', '.join(generate_rows)}])",
            *self._render_function(
                generate,
                f"def {generate.name}(target: fac.Output, value: object) -> None:",
                '""',
                ("value",),
            ),
            "    fac.write_text(target, text)",
            '    print("ran", target)',
            f"@fac.rule(each=[{compile_row} for source in SOURCES], flag={self.flag!r})",
            *self._render_function(
                compile_,
                f"def {compile_.name}(source: fac.Input, target: fac.Output, value: object, flag: object, headers: list[fac.OrderOnly] = GENERATED) -> None:",
                "expand(source, headers)",
                ("value", "flag"),
            ),
            "    fac.write_text(target, text)",
            '    print("ran", target)',
            "@fac.rule",
            *self._render_function(
                link,
                f'def {link.name}(objects: list[fac.Input] = OBJECTS, notes: fac.Input = "notes", first: fac.Output = fac.out({first!r}), second: fac.Output = fac.out({second!r}), level: object = {self.level!r}) -> None:',
                "join(objects, notes)",
                ("level",),
            ),
            "    fac.write_text(first, text)",
            "    fac.write_text(second, text.upper())",
            '    print("ran link")',
        ]


def subsets(items: list[_T], max_size: int = 2) -> st.SearchStrategy[tuple[_T, ...]]:
    """Return a strategy for up to `max_size` distinct members of `items`, which may be empty."""
    if not items:
        return st.just(())
    return st.lists(st.sampled_from(items), unique=True, max_size=max_size).map(tuple)


@st.composite
def projects(draw: st.DrawFn) -> Project:
    """Return a strategy for a member of the family whose every include resolves, and whose helpers mostly have a caller."""
    helpers = {
        f"u{index}": draw(_codes(f"u{index}", st.sampled_from(MODULES), st.sampled_from(_FORMS)))
        for index in range(draw(st.integers(2, 4)))
    }
    recipes = {name: draw(_codes(name, st.just("fac"), st.just(Form.PLAIN))) for name in RECIPES}
    for index, helper in enumerate(helpers.values()):
        later = list(helpers.values())[index + 1 :]
        callers = [
            *recipes.values(),
            *(code for code in later if MODULES.index(code.module) >= MODULES.index(helper.module)),
        ]
        caller = draw(st.sampled_from([*callers, None]))
        if caller is not None:
            caller.calls = (*caller.calls, helper.key)
    headers = [f"{directory}/{name}" for directory in HEADER_DIRECTORIES for name in HEADER_NAMES]
    project = Project(
        helpers=helpers,
        recipes=recipes,
        sources={},
        headers=dict.fromkeys(draw(subsets(headers)), INITIAL_TEXT),
        generated=dict.fromkeys(draw(subsets(list(HEADER_NAMES))), 0),
        notes=dict.fromkeys(draw(subsets(list(NOTE_NAMES))), INITIAL_TEXT),
    )
    resolvable = project.find_resolvable()
    for name in SOURCE_NAMES[: draw(st.integers(1, 2))]:
        project.sources[name] = Source(INITIAL_TEXT, draw(subsets(resolvable)))
    return project


@st.composite
def _codes(
    draw: st.DrawFn, key: str, modules: st.SearchStrategy[str], forms: st.SearchStrategy[Form]
) -> Code:
    module = draw(modules)
    usable = MODULES[: MODULES.index(module) + 1]
    reads = draw(subsets([(used, name) for used in usable for name in CONSTANTS]))
    return Code(key, module, reads=reads, form=draw(forms))


def _calc_reference(module: str, defining_module: str, name: str) -> str:
    return name if module == defining_module else f"{defining_module}.{name}"


def _indent(lines: list[str]) -> list[str]:
    return [f"    {line}" if line else line for line in lines]


def _render_source(source: Source) -> str:
    return "".join(
        f"{line}\n" for line in (source.text, *(f"#include {name}" for name in source.includes))
    )
