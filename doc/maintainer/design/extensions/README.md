# Extensions

An extension is a module that defines rules for reuse, importing only names in `facere.__all__`. The shipped extensions, `facere.c`, `facere.fetch`, `facere.git`, and `facere.uv`, follow the same rule, held to it by a CI check, so a project's own extension can do everything a shipped one does. Facere loads them on first use through a module `__getattr__`, so `import facere as fac` also reaches `fac.c`, and an invocation that never touches them skips their imports, `urllib.request` alone costing about 60 ms. An extension's helper defines rules by applying `fac.rule(each=..., name=...)` to one of its module functions, naming them after what they build, and returns the paths they output.

- [C support](./c.md) - before changing `facere.c`
- [Fetching](./fetch.md) - before changing `facere.fetch`
- [git repositories](./git.md) - before changing `facere.git`
- [uv projects](./uv.md) - before changing `facere.uv`
