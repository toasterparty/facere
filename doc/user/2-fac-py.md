# Writing a `fac.py`

## Rules

A rule is a function decorated with `@fac.rule`, and its signature declares what it reads and writes. Each parameter's annotation decides what it holds:

| Annotation | Holds |
| --- | --- |
| `fac.Input`, `list[fac.Input]` | Inputs, the files or directories the rule reads |
| `fac.OrderOnly`, `list[fac.OrderOnly]` | *(0.4)* Files or directories a rule's recipe may read, such as a generated header only some compiles include. They are built first, and a change to one's content makes the rule stale only once the recipe reports reading it through `fac.add_inputs`. A change to which paths the parameter holds does so only where the recipe's code names the parameter |
| `fac.Output`, `list[fac.Output]` | Outputs, the files or directories the rule writes. Every rule has at least one output, a file or a virtual output |
| `fac.VirtualInput`, `list[fac.VirtualInput]` | *(planned)* Virtual outputs of a [store](./5-virtual-outputs.md) the rule reads |
| `fac.VirtualOutput`, `list[fac.VirtualOutput]` | *(planned)* Virtual outputs of a store the rule writes |
| `str`, `list[str]` | A value that may look like a path, such as an entry a manifest lists, which the rule never reads as a file |
| Anything else, or none | A value: data the rule uses that is not a file, such as a flag or a version string |

Each parameter is filled from one of:

- its default
- a keyword argument to `@fac.rule`, which fills the parameter it names
- *(0.2)* `each=`, a list of dicts, which defines one rule per dict, each key filling the parameter it names. Every rule it defines shares the function's name. [Parameterization](./3-parameterization.md) shows each of these at work.

A default is read once, when `fac.py` loads, so a list default such as `titles: list[fac.Input] = TITLES` is safe here, though Python linters warn against one, as ruff's `B006` does.

A rule's name on the command line is its function's name, less one trailing underscore, so `def import_` is named `import`. Pass `name=` to `@fac.rule` or `@fac.task` to choose another.

The function's body is the rule's recipe. Facere executes it only when an output is needed and out of date, after creating each output's parent directory. Any exception it raises fails the rule, so an `assert` stops a bad result.

*(planned)* `@fac.rule(clear=True)` deletes every output before the recipe executes, for a tool that keeps what an earlier execution left, such as `ar r`, `zip`, or `uv build --out-dir`.

## Paths

Write paths as strings relative to the directory holding `fac.py`, with `/` separators on every OS. An unannotated value that names a file under the root is an error, since Facere cannot tell whether the rule reads it: annotate the parameter `fac.Input`, or `str` if the string only happens to look like a path.

Rules connect through paths and virtual outputs alone. A rule that inputs the paths or virtual outputs another writes executes after it, whatever order the rules are defined in. An input that no rule outputs is a source, and must exist.

Before executing any recipe, Facere loads `fac.py` and checks every rule, so a mistake such as two rules outputting one path, a missing source, or a dependency cycle fails at once, naming the `fac.py` lines involved.

`fac.out` places an output in the output directory, `build/` by default, at the same relative path as the file it comes from, with its suffix swapped when you pass one: `fac.out("pages/about.txt", ".html")` is `build/pages/about.html`, and `fac.out("sitemap.txt")` is `build/sitemap.txt`. *(0.2)* `fac.out()` is the output directory itself in the root `fac.py`, and its mirror of the `fac.py`'s own directory elsewhere. A rule may still output any path. Facere keeps its state, its record of past builds, in the output directory too, so deleting the directory forgets everything and the next build executes every rule.

*(0.2)* `fac.sources("pages/**/*.txt")` lists the files a glob matches, sorted, where `**` matches any number of directories. It skips the output directory, *(0.4)* any other directory a `--out` left, and hidden files, whose names start with `.`, unless the glob's own part starts with `.`, as in `fac.sources(".github/*.yml")`. Call it while `fac.py` loads, as for a parameter's default. *(0.4)* A rule can't input a directory holding the output directory, such as `.`, since its content changes on every build, so `fac.sources("**")` is how a rule reads every file in the project.

*(0.2)* `fac.read_text(path)` returns a text file's content, and `fac.write_text(path, text)` replaces a file with `text`. Both use UTF-8 and `\n` line endings on every OS, so an output's bytes are the same on every machine, which Python's `open` gives only when told its encoding and newline.

*(planned)* `fac.write_archive(path, directory, top=None)` writes every file under `directory` into a `.zip`, `.tar`, or `.tar.gz`, chosen by `path`'s suffix, inside a directory named `top`, or else `directory`'s own name. The same files give the same bytes on every machine, since members are sorted and times, owners, and modes are fixed.

## Commands

`fac.run` runs one command. In a rule it returns the command's standard output as text, and in a task, whose commands print live, it returns an empty string unless `quiet=True` *(0.3)*. It runs without a shell, so pass the program and each argument separately: `fac.run("pandoc", source)`, never `fac.run("pandoc about.txt")`. A list or tuple of strings passes each of its elements as one argument. A command that exits non-zero fails the recipe.

In a rule, a command reads an empty standard input and its output is printed once it finishes. Keyword arguments adjust that:

| Argument | Effect |
| --- | --- |
| `stdin=`, `stdout=`, `stderr=` | Name a file to read standard input from or write a stream to. A file both `stdout=` and `stderr=` name gets both streams |
| `env=` | Set environment variables over the inherited ones and those `fac.env` sets. `None` unsets a variable |
| `cwd=` | Run in another directory, relative to the root |
| `quiet=True` | Hide the command's output when it succeeds. *(0.3)* In a task, `fac.run` also returns the standard output as text, and the command reads an empty standard input as in a rule, so it can't prompt |
| `timeout=` | Kill the command after that many seconds, failing the recipe |

*(0.2)* `fac.env(LC_ALL="C")`, called while `fac.py` loads, sets a variable for every command, or unsets it with `None`. Calls may repeat a variable's value, but one that changes it fails, naming both calls. Unlike a variable inherited from your shell, it joins every rule's fingerprint, so changing it re-executes them.

## Tasks

A task is a function decorated with `@fac.task`, for work that must happen whenever you ask, such as running tests, a server, or a deploy. It takes inputs and values but no outputs, and executes every time `fac` is asked for it, after the rules that output its inputs. Its commands print live and read from the terminal.

*(0.2)* A task receives the arguments after `--` on the command line through a parameter annotated `fac.Args`, a tuple of strings. Without `--`, the parameter holds its default, or `()` when it has none.

```python
@fac.task
def serve(args: fac.Args, files: list[fac.Input] = SITE):
    fac.run(sys.executable, "-m", "http.server", args, "--directory", fac.out("pages"))
```

The decorators return the function unchanged, so a task may call another as plain Python, as a `test` task might call `lint` first. The call runs the body alone, without building what the called task inputs.

## When a rule executes

Facere compares content, never timestamps. A rule executes when any of these changes:

- the content of an input, which *(0.4)* outside Windows includes whether the file is executable, and for a link inside a directory input is its target's content
- the files in a directory input, when one appears or disappears
- *(0.4)* the paths a `fac.OrderOnly` parameter holds, where the recipe's code names that parameter, though never their content
- *(0.4)* the content of a file its recipe last reported through `fac.add_inputs`, wherever it lies, or a new file under the root, or a new output, with the name of one it reported, since a tool searching a path may find that first
- its recipe's code, or that of a function or class in your project the recipe reaches by name, such as a helper in `fac.py` or a shared module *(0.2)*, along with *(0.4)* the function a decorator wraps and the classes a class inherits from
- a value or module constant the recipe reads, directly or through such a function, *(0.4)* including the defaults such a function's parameters take. *(0.4)* A value counts by its content wherever `pickle` can take it apart, a dataclass, enum member, date, or compiled pattern included, and one it cannot, such as an open file or a lock, fails collection
- a variable `fac.env` sets *(0.2)*
- one of its outputs, deleted or edited by hand, and *(planned)* a virtual output changed in or missing from its store

*(0.4)* An input changed while its rule executes makes the rule execute again on the next `fac`, even where the change was undone, since the tool may have read it halfway. Where the same input changes during two executions in a row, as when a tool rewrites its own input, `fac` prints a warning naming the rule and the input. Comments, docstrings, and reformatting change nothing. A rule downstream executes only if an output it inputs comes out different. Facere cannot see what a recipe reads behind its back, such as an environment variable inherited from your shell or a file it never declared: [hidden inputs](./7-best-practices.md#hidden-inputs) lists each.

[<- Getting started](./1-getting-started.md) | [Parameterization ->](./3-parameterization.md)
