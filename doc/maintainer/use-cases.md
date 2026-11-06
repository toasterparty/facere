# Use cases

A design or requirement change that makes one of these awkward is raised before it lands.

- A mature C project:
    - `gcc` for building
    - `clang-format` for formatting
    - `clang-check` for static analysis
    - separate `server` and `client` binaries
    - `debug`, `release`, and `test` configurations of `gcc` flags, for build time, optimized output, and static analysis respectively
    - `-DENABLE_HTTPS=1`
    - runtime profiling
    - valgrind
    - a summary of static memory usage (`.text`, `.data`, `.bss`)
    - a command to increment the major, minor, or patch version
    - occasional inspection of the disassembly
- Building with the `gcc` found on `PATH`, failing if it is missing or older than 14.
- `fac flash -- -p /dev/ttyUSB0`, `fac flash -- --port /dev/ttyUSB0`, and `fac flash monitor`: build what flashing needs, then flash (a task), then monitor (a task).
- Cloning a dependency at a specific release tag.
- Cloning a dependency at the latest `origin/main` commit at the time of invocation.
- VS Code build tasks with a problem matcher.
- Building, or restarting, on save.
- Hot-swapping on save.
- `compile_commands.json` for an IDE.
- Many outputs that go stale independently, stored three ways, each with a `fac.py` as short and a no-op as cheap as the storage allows:
    - one file per output
    - one row per output, all in a single file
    - pages rendered from local files, each published to a CMS's HTTP REST API, with a local index built from what was published

The C project is driven like this:

```sh
fac                  # fac server.debug client.debug
fac all              # everything except tasks
fac server           # fac server.debug
fac '*.release'      # fac server.release client.release
fac 'server.*'       # fac server.debug server.test server.release
fac run.server.debug # build server.debug, then start that server
fac run              # fac run.client.debug
fac test             # clang static analysis, gcc static analysis with warnings as errors, unit tests:
                     # test.*, that is test.clang_check test.gcc test.unit, where test.gcc depends on '*.test'
```
