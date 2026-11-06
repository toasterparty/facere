# Best practices

Facere checks what it can see: undeclared paths *(planned)*, two rules outputting one path, an output changed after its rule finished *(planned)*, an output edited by hand. These practices cover what it cannot see. What your project builds is your decision, so each states what Facere will do, and you choose the rebuilds you want.

## Hidden inputs

These stay out of every fingerprint, so a change to one executes nothing until you declare it:

- **What a recipe reads while it executes** besides its inputs and values, such as an environment variable through `os.environ`, the time, the user, the host name, or the network.
- **Variables inherited from your shell**, which every command receives.
- **Files read without being declared**, such as a header a compile includes or a config file a tool finds on its own. Declare them as inputs, or report what a tool read through `fac.add_inputs` *(planned)*. Facere will fail a recipe that uses an undeclared file under the root *(planned)*. That check cannot see a path glued to its flag, as in `-Ibuild/gen`, or a file opened from a thread the recipe starts.
- **Code outside your project.** The standard library, Facere, and installed packages are hashed by name only, so upgrading Python, Facere, or a package executes nothing.
- **Code reached other than by name**, through a computed name such as `getattr(module, name)` or `importlib.import_module`, or through a value, such as a dict of handler functions.
- **Programs.** No program a command launches joins the fingerprint, so upgrading a compiler executes nothing. Declare one as an input, as with `compiler: fac.Input = shutil.which("cc")`, or pin its version in a value. Either way, what it runs indirectly, such as `as` and `ld` behind `gcc`, and the shared libraries it loads, stay out.
- **Files a rule writes but does not declare**, which Facere neither tracks nor rebuilds when edited by hand.
- **What a store cannot see** *(planned)*. Facere sees a store's virtual outputs only through its own `read` and `stamp`, so a `read` that skips part of its file, or a `stamp` that misses a change, leaves that part or that change untracked.

Two planned features bring narrower gaps of their own. A new file in a hidden directory can shadow a header that `fac.add_inputs` recorded without making its rule stale, and on Windows, which has no change time, the hash cache misses a same-size file replaced with its old modification time.

Facere works the same whether or not a recipe reads one of these: a header stamped with `datetime.now()` in its recipe holds the time of the rule's last execution. To make a change execute the rule instead, read the value at module level, where it joins the fingerprint: `STAMP = datetime.now().isoformat()` then executes what reads it on every invocation, and `os.environ.get("FLAVOR")` whenever the variable changes. Pass a per-run value to a task after `--` *(0.2)*.

A variable set in Python, through `env=` for one command or `fac.env` *(0.2)* for all of them, joins the fingerprint. That suits `LC_ALL` for a tool whose output follows the locale, such as `sort`, and `CPATH` or `PKG_CONFIG_PATH` where a compile or a configure script reads them. Setting one to `None` keeps a value a developer's shell exports from reaching the command.

## Immutable outputs

An output changes only by its own rule replacing it whole. Facere leaves the previous output in place when a rule executes again, and compares every output against its record, so:

- Never modify, move, or delete another rule's output. Write a new file from it instead, as `strip -o` does, and copy files into a directory you assemble from other rules' outputs. Moving a file out of another rule's output deletes that output, so the invocation fails, or the next one rebuilds it.
- Appending to your own previous output piles up content once per execution.
- Delete your own previous output before a tool that updates it in place: `ar r`, `zip`, `tar -r`, `uv build --out-dir`, `pip install --target`, and `shutil.copytree(dirs_exist_ok=True)` all keep what the last execution left, so a deleted source's object still links and an old wheel still gets published. Clear a directory output with `shutil.rmtree`, or *(planned)* mark the rule `clear=True` so Facere deletes its outputs before the recipe executes.

```python
# Bad: an object removed from OBJECTS stays in the library
@fac.rule
def library(objects: list[fac.Input] = OBJECTS, lib: fac.Output = LIBRARY):
    fac.run("ar", "rcsD", lib, objects)
```

```python
# Good
@fac.rule
def library(objects: list[fac.Input] = OBJECTS, lib: fac.Output = LIBRARY):
    if os.path.exists(lib):
        os.remove(lib)
    fac.run("ar", "rcsD", lib, objects)
```

```python
# Bad: the wheel and manual vanish from their rules' outputs
@fac.rule
def dist(wheel: fac.Input = WHEEL, manual: fac.Input = MANUAL, folder: fac.Output = DIST):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    shutil.move(wheel, folder)
    shutil.move(manual, folder)
```

```python
# Good
@fac.rule
def dist(wheel: fac.Input = WHEEL, manual: fac.Input = MANUAL, folder: fac.Output = DIST):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    shutil.copy2(wheel, folder)
    shutil.copy2(manual, folder)
```

## Tests and deploys

A task executes whenever asked, and a rule only when stale, so the choice decides when a test repeats. A test written as a rule keeps its cached pass until an input changes, however much else its verdict depends on, while a task gives a fresh verdict every time.

```python
# A pass stands until an input changes
@fac.rule
def tests(program: fac.Input = TEST_BINARY, log: fac.Output = TEST_LOG):
    fac.run(program, stdout=log)
```

```python
# Every request runs the tests
@fac.task
def tests(programs: list[fac.Input] = TEST_BINARIES):
    for program in programs:
        fac.run(program)
```

A rule that inputs a file a task writes treats it as a source, so the rule fails on a fresh clone and is never ordered after the task.

## Command arguments

Pass each argument separately, and do file work in Python. Facere runs commands without a shell, so `fac.run("mkdir -p build")` looks for a program named `mkdir -p build`. Reaching for a shell instead, through `os.system` or `shell=True`, ties the build to one platform's shell, and hides the paths from the undeclared-path check.

```python
# Bad: needs a POSIX shell, and Facere sees neither gcc nor the paths
subprocess.run(f"mkdir -p {obj_dir} && gcc -c {src} -o {obj}", shell=True, check=True)
```

```python
# Good
os.makedirs(obj_dir, exist_ok=True)
fac.run(CC, "-c", src, "-o", obj)
```

Give each path its own argument, or put it after `=`. `fac.run` *(planned)* checks each argument and the parts of a flag split at `=` and `,`, so a path glued to its flag, as in `-Tsrc/link.ld`, escapes the check, and editing an undeclared linker script never relinks the program.

## Identical outputs

A rule downstream executes only when an output it inputs comes out different, so an output that differs on every execution carries each one downstream. To stop downstream rules executing where nothing changed, write identical bytes:

- **Listings.** Sort `os.listdir`, `os.scandir`, `os.walk`, and `glob.glob`, which return filesystem order. `fac.sources` *(0.2)* is already sorted.
- **Sets.** A set of strings iterates in a different order in every process, so a list, a command, or file content built by iterating one changes between runs. A list built from one at module level changes the rule's fingerprint, so it executes every time. Use `sorted()`, or a `dict` for insertion order.
- **Archives.** `shutil.make_archive` records file mtimes, the current user, and the time. `fac.write_archive` *(planned)* fixes them, as do `zipfile` and `tarfile` with sorted items, fixed times, owners, and modes, and gzip's `mtime=0`. From the command line, use GNU `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner`, then `gzip -n`.

## Rule granularity

Write one rule per independent output and one per tool invocation. Facere re-executes a rule whole, so batching independent files re-executes them all when one changes. Splitting one invocation is worse: several rules each declaring one of its files all write every file, an undeclared race under `-j` *(planned)*. Batch only tools with a heavy startup, such as a JVM or Nuitka. Many small results that belong together, such as the rows of one table, stay one rule each as the virtual outputs of a [store](./5-virtual-outputs.md) *(planned)*, never one file each only to be tracked.

## Names for many rules

A name on the command line selects every rule its function defines, so `fac object_file` builds each object. Name the function for what one rule makes, in the singular, since a failure names one rule: `rule 'object_file' (build/main.o)`. `name=` replaces the name where the function's own would read badly on the command line, at the cost of the code and the command line calling the rules by different names.

## Orphaned outputs

Delete the old file yourself when you rename or remove an output, since Facere leaves it on disk, as it leaves a removed rule's virtual output in its store. An orphan does harm once something lists its directory: a linker search path finds an old `libfoo.a`, or `glob(f"{dist}/*")` uploads an old wheel. Input declared paths rather than listing a directory.

## Advanced

### Stamp files

Record what a rule did, never an empty stamp. Facere compares content, and a stamp's content never changes, so nothing that inputs it ever re-executes on its account. Write something that changes exactly when the result does, such as the installed package list or a tool's `--version` output.

```python
# Bad: consumers never see an install change
@fac.rule
def install(lock: fac.Input = "package-lock.json", stamp: fac.Output = fac.out("npm.stamp")):
    fac.run("npm", "ci")
    open(stamp, "w").close()
```

```python
# Good
@fac.rule
def install(lock: fac.Input = "package-lock.json", record: fac.Output = fac.out("npm-ls.txt")):
    fac.run("npm", "ci")
    fac.run("npm", "ls", "--all", stdout=record)
```

### Module-level code

Module-level code runs on every invocation, `--list` and `--check` *(planned)* included, so a probe there costs its spawn each time. A rule's output read there holds the previous run's content, so the build lags one run behind, and fails on a fresh clone. To make a program count without a spawn, [declare it as an input](#hidden-inputs). To check its version, probe in a rule marked `always=True` *(planned)* whose output its consumers input, so they execute only when the version changes, and a missing or old gcc fails every invocation that needs it:

```python
@fac.rule(always=True)
def gcc_version(path: fac.Output = GCC_VERSION):
    version = fac.run("gcc", "-dumpversion", quiet=True).strip()
    assert int(version.split(".")[0]) >= 14, f"gcc 14 or newer required, found {version}"
    fac.write_text(path, f"{version}\n")
```

### Scratch files

Name every scratch file after one of the rule's own outputs, since output paths are unique. Facere cannot see writes: two rules writing one undeclared path, such as a shared depfile name, race under `-j` *(planned)* and the invocation still passes. Never read another rule's scratch file, since that orders nothing.

Once a tool succeeds, report what it read through `fac.add_inputs` *(planned)*, or editing a header it read re-executes nothing. For C, `fac.c.makefile_deps` *(planned)* reads that list from the compiler's depfile.

```python
# Bad: every compile writes the same depfile
fac.run(CC, CFLAGS, "-MD", "-MF", fac.out("deps.d"), "-c", src, "-o", obj)
```

```python
# Good
fac.run(CC, CFLAGS, "-MD", "-MF", f"{obj}.d", "-c", src, "-o", obj)
fac.add_inputs(fac.c.makefile_deps(f"{obj}.d"))
```

Keep a tool's deliberate incremental state, such as MSVC's `/INCREMENTAL` or `tsc`'s `.tsbuildinfo`, in a scratch file named after the rule's output, and turn it off for release outputs.

Point caches that tools drop beside the sources into the output directory, or turn them off, or `fac.sources` *(0.2)* globs pick them up as inputs: `PYTHONPYCACHEPREFIX` for `__pycache__`, and `--cache-dir` where a tool offers one. Hidden caches, such as `.pytest_cache`, need nothing, since globs skip hidden paths unless the glob names them.

### Generated file names

Declare every file a generator writes, deriving the names at collection, as from each spec's name, or passing the tool a flag that fixes them. A file a generator names for itself is an undeclared scratch file, which a rule can read without being ordered after the generator. Where the names cannot be known, declare the directory as one output and consume it in one rule.

```python
# Good: protoc's names follow from each spec's
PROTO_RULES = [
    {"spec": spec, "source": fac.out(spec, ".pb.cc"), "header": fac.out(spec, ".pb.h")}
    for spec in PROTOS
]


@fac.rule(each=PROTO_RULES)
def proto(spec: fac.Input, source: fac.Output, header: fac.Output):
    fac.run("protoc", f"--cpp_out={fac.out()}", spec)
```

### Network access

*(planned)* An ordinary rule with an unpinned download executes only when Facere would rebuild its output anyway, so the data stays as it was. Passing `sha256=` to `fac.fetch` pins it, and `always=True` fetches on every invocation, with its consumers executing again only when the bytes change. A store over HTTP *(planned)* asks for its stamp once in every build that needs its virtual outputs, so a stamp the server keeps cheap, such as a collection's ETag, costs least.

### Minimum version

Omit `fac.minimum_version` unless the `fac.py` may meet a Facere older than the latest release, as on machines that upgrade Facere on a schedule of their own. There, call it at the top of `fac.py` with the oldest release whose behavior the file relies on, as in `fac.minimum_version("0.2")`, so an older Facere fails at once, naming how to upgrade, rather than misread the file.

[<- Debugging and tracing](./6-debugging.md) | [Terminology ->](./8-terminology.md)
