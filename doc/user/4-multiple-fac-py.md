# Multiple `fac.py` files

`fac` loads one `fac.py`, the root's, and that file can build a whole tree. Parts built and versioned apart can each keep a `fac.py` of their own.

## Sharing code

Put settings and helper functions a `fac.py` shares with other modules in an ordinary Python module under its root, and import it. Each project's imports reach only modules under its own root, until *(planned)* one graph spans them:

```python
from tools.settings import BASE_URL
```

*(0.2)* Facere fingerprints a shared module's code like the `fac.py`'s own, so a change to a function or constant executes just the rules that reach it. A rule or task defined by importing another `fac.py` fails, since each one defines its own project.

## Separate projects

Today a subdirectory holding a `fac.py` is a project of its own, with its own rules and its own `build/`. Run it from anywhere with `-C`:

```
$ fac -C lib
Finished in 16ms. No work to do. 1 output up to date.
```

A task in the root can drive it, running the same Facere that runs the root:

```python
@fac.task(default=True)
def everything():
    fac.run(sys.executable, "-m", "facere", "-C", "lib")
```

The two graphs stay apart, so a root rule cannot order itself after a rule in `lib/`. Where it must, give both rules to one `fac.py`.

## One graph *(planned)*

The root's `fac.py` will load first, followed by every other `fac.py` under the root, all joining one graph:

- Paths in a `fac.py` are relative to its own directory.
- Names are dotted by directory, so `fac lib.test` reaches `test` in `lib/fac.py`.
- `fac.exclude` keeps out a directory, such as a vendored dependency shipping a `fac.py` of its own.
- `@fac.override` lets a `fac.py` adjust how the rules reading files under its own directory are built, such as one component's optimization flags, with no edit outside that directory.

[<- Parameterization](./3-parameterization.md) | [Virtual outputs ->](./5-virtual-outputs.md)
