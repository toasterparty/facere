# Facere

Facere is a build tool configured in plain Python. Rebuild exactly what changed, and never `make clean` to recover from a stale build. Rules are Python functions in a `fac.py`. Facere tracks file content, flags, and recipe code, so a changed flag recompiles, a touched file does not, and an output edited by hand is rebuilt. Collecting `fac.py` files from across a source tree is planned.

Read [`doc/user/`](./doc/user/README.md), which ships with every install, to install Facere and write a `fac.py`, and [`doc/maintainer/`](./doc/maintainer/README.md) before changing Facere itself.
