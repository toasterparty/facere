# C support

## Requirements

- Sources to objects to an executable MUST remain the shortest `fac.py` Facere can express.
- Header tracking, response files, and clang's `compile_commands.json` for editors MUST ship in `facere.c`.
- Adding a source file or a directory of sources to a project MUST NOT require a `fac.py` edit. Giving one directory flags of its own MUST NOT require an edit outside that directory.
- `facere.c` MUST NOT require a list of include directories, linked libraries, or defines kept per consumer.

## Conventions

The defaults assume three conventions, which leave the sources as the only record of what depends on what.

| Usually kept by hand | Derived instead from |
|---|---|
| Include directories per consumer | One `-I` at the root, with headers included by their path from the root, as in `#include "net/socket.h"`, which also keeps header names from colliding |
| Libraries linked per program | One static library of the shared code, and each program's private code in a directory of its own, linked only into that program. Within one archive, two programs' definitions of one symbol would link whichever member the linker met first, with no error |
| Public defines | Settings a header depends on live in a header, checked in or generated and declared as an input, so every consumer sees the same values |

Where shared code truly must compile differently per program, such as an `#ifdef SERVER` in `src/common/`, the conventions first move the difference into a header or into the program's own directory. If it cannot move, the program's own configuration scope archives its own copy of the shared code, at the visible cost of compiling it twice per configuration.

## API

A `Toolchain` holds a compiler and the flags every call would otherwise repeat. Its methods and `compile_commands` define their rules when called, at collection, place every output with `fac.out()`, so they follow the open `fac.scope`, and take `default=True`, passed on to their rules. They name an executable's rule after its program, a library's after its file's stem, such as `libcommon`, and every compile `object_file`, so an override or `fac.rules` reaches every compile through one function. `inputs` joins every compile a method defines as order-only inputs, for a generated header that must exist before the first compile.

| Name | Provides |
|---|---|
| `Toolchain(cc="gcc", ar="ar", cflags=(), ldflags=())` | a compiler and its flags |
| `.object_files(sources, inputs=())` | one object file per source, returning the objects in order. Each depfile is deleted once its headers are recorded, as ninja's `deps = gcc` mode does, since the state keeps them |
| `.static_library(path, sources, inputs=())` | the sources compiled and archived, deleting the old archive first, since `ar` keeps members whose sources are gone |
| `.executable(path, sources, libraries=(), inputs=())` | the sources compiled and linked into one program |
| `.executables(mains, libraries=(), inputs=())` | one program per main, named after it, each linked against the libraries |
| `compile_commands(scope=None)` | `compile_commands.json` at the top of the current scope's output directory, for every compile `facere.c` defines in that scope, or in the scopes the pattern `scope` matches, so a root call such as `compile_commands(scope="*.debug")` gathers one configuration from every program |
| `makefile_deps(path)` | the files a depfile lists, for `fac.add_inputs`, in the Makefile-fragment format that gcc, clang, nvcc, and `rustc --emit=dep-info` share |

The shortest project is one call:

```python
import facere as fac

fac.c.Toolchain().executable("app", fac.sources("src/*.c"), default=True)
```

Every helper applies `fac.rule` as a plain call to a module function, so no decorator runs at the extension's import:

```python
@dataclass
class Toolchain:
    cc: str = "gcc"
    ar: str = "ar"
    cflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)

    def object_files(self, sources, inputs=(), default=False):
        """Compile each C source to an object file, tracking the headers it includes."""
        objects = [fac.out(src, ".o") for src in sources]
        fac.rule(
            each=[{"src": src, "obj": obj} for src, obj in zip(sources, objects)],
            cc=self.cc,
            cflags=self.cflags,
            inputs=inputs,
            default=default,
        )(object_file)
        return objects


def compile_args(src, obj, cc, cflags):
    return [cc, *cflags, "-MD", "-MF", f"{obj}.d", "-c", src, "-o", obj]


def object_file(src: fac.Input, obj: fac.Output, cc, cflags, inputs: list[fac.OrderOnly]):
    fac.run(*compile_args(src, obj, cc, cflags))
    fac.add_inputs(makefile_deps(f"{obj}.d"))
    os.remove(f"{obj}.d")


def compile_commands(scope=None, default=False):
    """Write compile_commands.json for every compile in the current scope, or in the scopes scope matches."""
    path = fac.out(fac.from_root("compile_commands.json"))
    if scope is None:
        compiles = fac.rules(object_file, under=fac.out(fac.from_root(".")))
    else:
        compiles = fac.rules(object_file, scope=scope)
    fac.rule(
        path=path, compiles=compiles, root=os.getcwd(), name="compile_commands", default=default
    )(write_compile_commands)
    return path


def write_compile_commands(path: fac.Output, compiles, root):
    entries = [
        {
            "directory": root,
            "file": c["src"],
            "arguments": compile_args(c["src"], c["obj"], c["cc"], c["cflags"]),
            "output": c["obj"],
        }
        for c in compiles
    ]
    fac.write_text(path, json.dumps(entries, indent=1))
```

`compile_commands` builds from the compiles' arguments through `fac.rules`, so it may be called from any `fac.py`, sees overrides, and exists before the first compile. clang reads its `directory` field verbatim rather than against the file's location, so the root's absolute path is one of its values, and moving the checkout rebuilds it.

Compiles pass `-MD` rather than `-MMD`, so the depfile lists headers found through `-isystem` too, and `fac.add_inputs` drops the system headers outside the root. A vendored dependency can then be included with `-isystem`, exempt from the project's warnings, and a new pin still recompiles its consumers. Since the depfile names every header, a new header that would shadow one of them, such as a root `cJSON.h`, recompiles the files that included the original.

`static_library`, `executable`, and `executables` measure each command line as the recipe executes. Past the platform limit, about 32 K characters on Windows, the recipe writes the objects to a temporary response file, deleted once the command finishes, and passes `@file` to the archiver or linker. `executable` and `executables` append `.exe` on Windows and return that path, so a program's path differs by platform while its name does not.

## Many directories

With the conventions, one root `fac.py` builds a project of many directories, and adding a directory or a program takes no edit:

```python
cc = fac.c.Toolchain(cflags=["-O2", "-Wall", "-Wextra", "-I."])

COMMON = cc.static_library("libcommon.a", fac.sources("src/common/**/*.c"))
for main in fac.sources("apps/*.c"):
    program = main.removeprefix("apps/").removesuffix(".c")
    cc.executable(
        program, [main, *fac.sources(f"src/{program}/**/*.c")], libraries=[COMMON], default=True
    )
fac.c.compile_commands(default=True)
```

A directory that needs flags of its own says so in a `fac.py` beside its sources, which the root never mentions:

```python
# src/common/crypto/fac.py
@fac.override(fac.c.object_file)
def faster(rule):
    rule.cflags = [*rule.cflags, "-O3"]
```

gcc honors the last `-O` it sees, and since GCC 5 per-function optimization options survive LTO, so such an override holds through a release link. A directory that needs rules of its own, such as generated code, gets its own `fac.py`, and the root names what it builds by writing the path, or through a constant both import from `tools/build.py`. That is the one cross-file line anyone maintains, and omitting it fails the link with an undefined symbol rather than going stale.

## Configurations

A configuration compiles the same source differently, so each needs its own objects and its own output directory: one `fac.scope` per configuration, inside one scope per program, so names read program first, as in `server.release`. Programs built mostly from the same objects share them through a `common` scope archived once per configuration, which each program links by path. A vendored dependency gets a toolchain of its own that takes each configuration's optimization and sanitizer flags, so ASan sees one consistent program, but not the project's warnings or `-Werror`. Release archives LTO objects with `gcc-ar`, which plain `ar` may not understand.

## Future work

MSVC. Its flags differ throughout, its header list comes from `cl /showIncludes` rather than a depfile, and `cl` requires the `INCLUDE`, `LIB`, and `LIBPATH` that Visual Studio's setup script computes, which a rule records by running `vcvarsall.bat`, as [execution](../execution.md#environment) describes.

## Open risks

- **Relinking.** Any changed object rebuilds its library, and every program relinks against it, though compiles stay precise.
- **Every compile waits for every generated header** in the first invocation, since `inputs=` orders them all before any compile.
