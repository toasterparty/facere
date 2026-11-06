# Writing `fac.py` examples

A `fac.py` in `doc/examples/`, and every `fac.py` snippet in `doc/user/`, teaches a reader who may know only beginner Python. Each uses the least Python that does the job, even where Facere's own code would reach for more. The root `fac.py` is the exception: it is checked by Facere's own lint and must run on `MINIMUM_FACERE`.

A `fac.py` needs only `import`, module constants, functions, the two decorators, `name: annotation = default` parameters, strings and f-strings, lists, dicts, `for`, `if`, `assert`, comprehensions over one list, and, for a store, a plain class with `__init__` and methods.

| Instead of | Write |
| --- | --- |
| `-> None`, or annotations on a helper | An annotation only where Facere reads one, so every annotation means something |
| `zip`, tuple rows, or tuple unpacking to feed `each=` | One dict per rule in a constant named for the function, such as `OBJECT_FILE_RULES` for `object_file`, with any other list of their paths read back out of it |
| A keyword argument to `@fac.rule` for a single rule's path | A parameter default |
| Inline paths beside named ones in one signature | All inline, or all named constants defined earlier |
| `[*a, *b]` | `a + b` |
| `*args` to pass a list to `fac.run` | The list itself, which `fac.run` expands |
| `open` with `encoding=` and `newline=` | `fac.read_text` and `fac.write_text` |
| `fac.out(".")` | `fac.out()` |
| `shutil.rmtree(path, ignore_errors=True)` | `if os.path.exists(path): shutil.rmtree(path)`, which still fails on a file it cannot delete |
| A dataclass, `NamedTuple`, `slots`, or `collections.abc` annotations | A dict for data, a plain class for a store |
| A leading underscore on a helper | A plain name, since nothing imports a `fac.py` |
| `name=` to make a plural | The function's own name, singular |
| `posixpath` or `os.path` splitting to get a file's stem | `PurePosixPath(path).stem` |
| `functools`, closures, `lambda`, `map`, or regex lookarounds | A loop or a helper function, or a module under the root that the `fac.py` imports |

`test/examples/test_style.py` enforces the rows a syntax tree can show.

Where an example needs something beyond this list, the gap is a candidate for Facere to fill, as `fac.write_text` was and `fac.write_archive` will be: raise it rather than teach the workaround.
