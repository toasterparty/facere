# Example: debug and release

One C program compiled twice from the same sources, each configuration with flags and a directory of its own, from plain loops over one table in [`fac.py`](./fac.py). It needs `uv`, whose `uvx` runs the compiler. [Parameterization](../../user/3-parameterization.md) explains the pattern.

| Action | Executes | Why |
|---|---|---|
| `fac` | 4 compiles, 2 links | Nothing is recorded yet |
| `fac` | none | Every fingerprint matches |
| `fac build/release/app` | none, or the release build alone | A path names one program and what it needs |
| Change release's `BUILD_NAME`, then `fac` | release's 2 compiles and link | Both compiles read the flag, and debug's flags did not change |
| Edit `src/greeting.h`, then `fac` | 4 compiles, then a link for each configuration whose objects changed | Every compile inputs every header |
| `fac run_release -- a b` | the release build if stale, then the program | A task always executes, and gets what follows `--` |
| `fac clean`, then `fac` | `clean`, then 4 compiles, 2 links | Deleting `build/` forgets every record |
