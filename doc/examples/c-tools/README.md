# Example: C tooling

One C program and the tools a mature project runs around its build, each a task, as in [`fac.py`](./fac.py). Compiling needs `uv`, whose `uvx` runs the compiler, and each other tool is needed only by the task that runs it: `clang-format`, `clang-check`, `size` and `objdump` from binutils, and `valgrind`. [`tools/flash.py`](./tools/flash.py) stands in for a flashing tool, so `flash` and `monitor` run with no board attached: the port is a file, which `monitor` runs.

| Action | Executes | Why |
|---|---|---|
| `fac` | 2 compiles, the link | Nothing is recorded yet |
| `fac app` | none | Every fingerprint matches |
| `fac bump app -- minor`, then `fac run` | `bump`, `main.c`'s compile, the link, then `run` | A task finishes before the targets after it start, and only `main.c`'s depfile lists `src/version.h` |
| `fac format` | `format`, which rewrites the sources in place | A reformatted source is a changed source, so the next `fac` compiles it |
| `fac check` | `check`, with no build | It inputs only sources, and `clang-check` reads what `-I.` finds |
| `fac size` | the build if stale, then `size` | The static memory summary, `.text`, `.data`, and `.bss` |
| `fac disassemble -- net_scheme` | the build if stale, then `disassemble` | The arguments after `--` go to the task, and its default applies without them |
| `fac valgrind` | the build if stale, then `valgrind` | Fails on any error valgrind finds |
| `fac flash -- -p build/other`, or `fac flash -- --port build/other` | the build if stale, then `flash` | The last `--port` wins, so the task's arguments override its default port |
| `fac flash monitor` | the build if stale, `flash`, then `monitor` | Targets execute in the order given |
| Set `-DENABLE_HTTPS=0` in `CFLAGS`, then `fac` | 2 compiles, the link | `cflags` joins each compile's fingerprint. A keyword argument to `@fac.rule` fills that parameter in every rule its function defines |
| `fac -v` after a change | what the change made stale | `-v` prints each command as one string |
| `fac -q` after a change | what the change made stale | `-q` hides each successful command's output |
| `fac --out other` | 2 compiles, the link, under `other/` | `--out` moves the output directory and the state inside it, so `build/` stays as it was |
| `fac clean`, then `fac` | `clean`, then 2 compiles, the link | Deleting `build/` forgets every record |
