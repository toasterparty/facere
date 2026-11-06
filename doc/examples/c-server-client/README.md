# Example: a C server and client, three ways

> **Status:** planned. This example uses `facere.c`, `facere.fetch`, `fac.scope`, and `fac.override`, which no release supports yet, so it does not run on the current release.

It uses [C support](../../maintainer/design/extensions/c.md) and [Fetching](../../maintainer/design/extensions/fetch.md).

A server that answers a name with `{"hello":"<name>","sum":<checksum>}`, and a client that checks the sum and turns the answer into a greeting. They share their message code, a checksum codec, and cJSON, which is fetched during the run rather than vendored. Each is made three ways from one graph, following [Design](../../maintainer/design/README.md): debug for observability and fast builds, test for the most validation, and release for speed and size. `echo world | build/server/debug/server | build/client/debug/client` prints `hello, world`.

```
.clangd                     points clangd at build
.gitignore                  build/ and third_party/
fac.py                      the configurations and the whole build
apps/client.c
apps/server.c
src/client/render.c
src/client/render.h
src/common/codec/checksum.c
src/common/codec/checksum.h
src/common/codec/fac.py     builds the codec for size in release
src/common/message.c
src/common/message.h
src/server/reply.c
src/server/reply.h
tests/test_message.c
```

## fac.py

[`fac.py`](./fac.py) holds the configurations and the whole build.

| Configuration | Goal | How |
|---|---|---|
| debug | observable, quick to make | `-O0` compiles fastest and keeps every variable. `-g3` adds macro definitions to the debug info. Frame pointers make profilers and stack traces reliable. No LTO, so links stay fast |
| test | catch as much as possible | AddressSanitizer and UBSan, with `-fno-sanitize-recover=all` so the first problem aborts. `-fanalyzer` runs GCC's static analyzer on every project compile, and `-Werror` turns every warning, analyzer findings included, into a failure |
| release | fast and small | `-O2` with LTO. Function and data sections plus `--gc-sections` drop unused code, `-s` strips symbols, and `-DNDEBUG` removes asserts |

Each program is an outer block holding one block per configuration, so names read program first: `server.release` is the release server, `fac server` makes the debug one, its block's default, and `fac '*.release'` makes every program's release build. The shared code is a block of its own, `common`, archived once per configuration, and each program links its configuration's libraries by path. The test binaries are one more such block, `tests`. Every program's configuration has a `run` task, decorated inside the block so it belongs to that configuration: `fac server.debug.run` makes the debug server and starts it, passing anything after `--`, and `fac 'tests.*.run'` runs every configuration's tests. The programs and the debug `compile_commands.json` are the defaults, so a plain `fac` makes the debug programs and what clangd reads.

## Configurations and programs

The configurations and the two programs are different kinds of split. A configuration compiles the same source differently, so each needs its own objects and its own output directory. The server and client are different programs made mostly from the same objects, so their shared objects live in `common`'s output directory for each configuration, and `src/common/` compiles once per configuration rather than once per program. Each program's own directory holds only its private objects and its link.

The shared code is its own library, and each program's private code joins only that program, as the C conventions require, so a `handle_message` defined on both sides never links the wrong one. Separate code also keeps ownership visible in the tree. A test that reaches into one program's internals makes that program's directory a library as well and links it ahead of `common`.

Where shared code truly must compile differently per program, such as an `#ifdef SERVER` in `src/common/`, the C conventions first move the difference into a header or into the program's own directory. If it cannot move, the program's own configuration block archives its own copy of the shared code, at the visible cost of compiling it twice per configuration.

## A component's own flags

The codec wants `-Os` in release, where its size matters more than its speed, and keeps that decision beside its source. [Its `fac.py`](./src/common/codec/fac.py) overrides the compiles of its own files, and the root knows nothing of it: the codec compiles into `libcommon.a` with the rest of `src/common/`, and deleting the codec's `fac.py` returns it to the configuration's flags. gcc honors the last `-O` it sees, so `-Os` overrides the configuration's `-O2`, and since GCC 5 per-function optimization options survive LTO, the release link does not undo it.

## Dependencies

cJSON gets its own toolchain, which takes each configuration's optimization and sanitizer flags, so ASan sees one consistent program, but not the project's `checks`, since third-party code is not held to its warnings, analyzer, and `-Werror`. Its header is included through `-isystem`, which exempts it from them in the project's compiles too, and `facere.c`'s `-MD` keeps it in the depfile, so a new cJSON pin recompiles `message.c`. `gcc-ar` archives the LTO objects of the release configuration, which plain `ar` may not understand.

`cjson` is defined once, outside the loop, and unpacks into the git-ignored `third_party/cjson/`, which every configuration shares. Defined inside the loop, it would make two rules output one path. The shared library inputs `cJSON.h` because `message.c` includes it, and it does not exist until the archive unpacks. The depfile would add it only after the first compile.

GitHub generates tag archives on demand and has changed their bytes before, which breaks every pin at once. A release asset or a mirror makes a sturdier pin where one exists.

## Tests

Every configuration's test binaries have their `run` task, since a release build can expose bugs a debug build hides. A task runs whenever requested, so `fac tests.debug.run` makes whatever the test binaries need and runs them, a failing test failing the task, and `fac 'tests.*.run'` runs every configuration's. The tests are not a default, so a plain `fac` stays quick enough for every save.

## Output directory

```
build/
    .fac/                           facere's state
    third_party/cjson.tar.gz        the downloaded cJSON archive
    compile_commands.json           every debug compile, for clangd
    common/
        debug/
            src/common/message.o  src/common/codec/checksum.o
            third_party/cjson/cJSON.o
            libcommon.a  libcjson.a
        test/                       the same files, sanitized and analyzed
        release/                    the same files, optimized, the codec's for size
    server/
        debug/
            server  apps/server.o  src/server/reply.o
        test/  release/             the same files, sanitized, or optimized and stripped
    client/                         laid out as server/
    tests/
        debug/
            tests/test_message  tests/test_message.o
        test/  release/
third_party/cjson/                  the unpacked cJSON tree, shared by every configuration
```

Each depfile is deleted once parsed, its headers kept in the state. Deleting `build/` forgets every record and the downloaded archive, while the unpacked cJSON tree stays.

## Runs

| Action | Executes | Why |
|---|---|---|
| `fac` | fetch, then in debug: 7 compiles, 2 archives, 2 links, `compile_commands.json` | Nothing is recorded yet |
| `fac` | nothing | Every fingerprint matches, and the fetch touches no network because `cjson` is up to date |
| `fac server.release` | in release: 5 compiles, 2 archives, the server's link | Only what the server needs: the shared code, the codec among it, cJSON, and the server's own two files |
| `fac tests.debug.run` | in debug: 1 compile, the test's link, then the test | Only the test binary was missing, and a task always runs |
| `fac tests.debug.run` | the test | A task always runs, and its binary is up to date |
| `fac 'tests.*.run'` | in test and release: the test binaries and what they need, then every configuration's test | The fetch is shared and already up to date |
| `fac common.release.libcommon` | nothing | The release library is already up to date |
| Delete `src/common/codec/fac.py`, then `fac '*.release'` | in release: 3 compiles, `libcommon.a`, 3 links | The codec's compile saw its `cflags` change, the client, never made in release before, compiles its own two files, and the release test binary relinks against the new library |
| Add `src/common/log.c`, then `fac` | in debug: 1 compile, `libcommon.a`, 2 links, `compile_commands.json` | The glob lists a new path, so the library's inputs changed |
| Edit `src/client/render.c`, then `fac` | in debug: 1 compile, the client's link | The server and the shared library never read it |
| Edit `src/common/message.h`, then `fac` | in debug: 3 compiles, `libcommon.a`, then each link whose inputs changed | Three depfiles recorded the header: `message.c`, `reply.c`, and `client.c`. No compile's arguments changed, so `compile_commands.json` stays up to date, and `test_message.c` recompiles at the next `fac tests.debug.run` |
| Add a `cJSON.h` at the root, then `fac` | in debug: 2 compiles, then whatever their objects change | Both `message.c`'s and `cJSON.c`'s depfiles recorded a `cJSON.h`. gcc now finds the new one first for `message.c` through `-I.`, while `cJSON.c` finds its own beside it and recompiles to the same bytes |
| Change release's `-O2` to `-O3` in both lists, then `fac '*.release'` | in release: everything the programs and tests need but the fetch | Every compile's `cflags` and every link's `ldflags` changed |
| Edit `third_party/cjson/cJSON.c`, then `fac` | fetch | An output no longer matches its recorded hash, so `cjson` unpacks the archive kept in `build/` again, without the network, and the restored bytes leave every `cJSON.o` up to date |
| Delete `build/`, then `fac` | everything the first run did, the download included | The state and the archive went with it, so nothing is recorded |

Scripts can address the same rules by path: `fac build/` makes every configuration in one parallel run, and `fac build/server/release/server` the release server.

`-v` prints each command and names why each rule executes. For the edit to `render.c`:

```
$ fac -v
build/client/debug/src/client/render.o: inputs changed (src/client/render.c)
gcc -O0 -g3 -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Wshadow -Wconversion -I. -isystem third_party/cjson -MD -MF build/client/debug/src/client/render.o.d -c src/client/render.c -o build/client/debug/src/client/render.o
build/client/debug/client: inputs changed (build/client/debug/src/client/render.o)
gcc build/client/debug/apps/client.o build/client/debug/src/client/render.o build/common/debug/libcommon.a build/common/debug/libcjson.a -o build/client/debug/client
```
