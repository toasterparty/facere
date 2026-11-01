# Facere

Facere is a build tool configured in plain Python. Rebuild exactly what changed, and never `make clean` to recover from a stale build. Rules are plain Python functions in `fac.py` files collected from across a source tree. Facere tracks file content, flags, recipe code, and the compilers themselves, so a changed flag recompiles, a touched file does not, and an output edited by hand is rebuilt.

## Using Facere

- [Getting started](./doc/user/getting-started.md) - first, to install Facere and write a `fac.py`
- [Best practices](./doc/user/best-practices.md) - before writing rules for a real project
- [Terminology](./doc/user/terminology.md) - when a term in these pages is unfamiliar

## Developing Facere

Read [`doc/maintainer/`](./doc/maintainer/README.md) before changing Facere itself.
