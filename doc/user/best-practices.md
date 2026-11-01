# Best practices

Facere checks what it can see: undeclared paths, two rules outputting one path, an output changed after its rule finished, an output edited by hand. Follow these practices for what it cannot see. Most come down to one principle: make a rule's outputs depend on its declared inputs and values alone, so rerunning it over its previous output gives the bytes a clean tree would.

## Immutable outputs

Never modify, move, or delete another rule's output. Write a new file from it instead, as `strip -o` does.

Copy files into a directory you assemble from other rules' outputs, such as one to archive. Moving a file out of another rule's output deletes that output, so the run fails, or the next run rebuilds it.

```python
# Bad: the wheel and manual vanish from their rules' outputs
@fac.rule
def dist(
    wheel: fac.Input = WHEEL, manual: fac.Input = MANUAL, folder: fac.Output = fac.out("dist")
):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    shutil.move(wheel, folder)
    shutil.move(manual, folder)
```

```python
# Good
@fac.rule
def dist(
    wheel: fac.Input = WHEEL, manual: fac.Input = MANUAL, folder: fac.Output = fac.out("dist")
):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    shutil.copy2(wheel, folder)
    shutil.copy2(manual, folder)
```

## Previous outputs

Write each output whole, never appending: Facere leaves the previous output in place, so appended content piles up once per rerun.

Delete your own previous output before a tool that updates it in place: `ar r`, `zip`, `tar -r`, `uv build --out-dir`, `pip install --target`, and `shutil.copytree(dirs_exist_ok=True)` all keep what the last run left, so a deleted source's object still links and an old wheel still gets published. Clear a directory output with `shutil.rmtree`.

```python
# Bad: an object removed from OBJECTS stays in the library
@fac.rule
def library(objects: list[fac.Input] = OBJECTS, lib: fac.Output = fac.out("libapp.a")):
    fac.run("ar", "rcsD", lib, objects)
```

```python
# Good
@fac.rule
def library(objects: list[fac.Input] = OBJECTS, lib: fac.Output = fac.out("libapp.a")):
    if os.path.exists(lib):
        os.remove(lib)
    fac.run("ar", "rcsD", lib, objects)
```

## Stamp files

Record what a rule did, never an empty stamp. Facere compares content, and a stamp's content never changes, so nothing that inputs it ever reruns on its account. Write something that changes exactly when the result does, such as the installed package list or a tool's `--version` output.

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

## Hidden inputs

Read nothing in a recipe but its inputs and values. Whatever else it reads stays out of its fingerprint, so changing it never reruns the rule: `os.environ`, `datetime.now()`, `getpass.getuser()`, `socket.gethostname()`. Write the value as a module constant instead. Put a per-machine value in a shared module kept out of version control, and pass a per-run value to a task after `--`.

The same holds for the environment your commands inherit from the shell, which Facere passes on without fingerprinting it. Set every variable that changes what a tool writes in Python, through `env=` for one command or `fac.env` for all of them, so its value joins the fingerprint: `SOURCE_DATE_EPOCH` from a release date beside `VERSION`, `LC_ALL` for a tool whose output follows the locale, such as `sort`, and `CPATH` or `PKG_CONFIG_PATH` where a compile or a configure script reads them. Setting a variable to `None` unsets it, so one a developer's shell exports never reaches the command.

```python
# Bad: the time joins no fingerprint, so BUILT keeps the first build's time until VERSION changes
@fac.rule
def version_header(path: fac.Output = fac.out("version.h")):
    stamp = datetime.datetime.now().isoformat()
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(f'#define VERSION "{VERSION}"\n#define BUILT "{stamp}"\n')
```

```python
# Good
@fac.rule
def version_header(path: fac.Output = fac.out("version.h")):
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(f'#define VERSION "{VERSION}"\n#define RELEASED "{RELEASE_DATE}"\n')
```

## Command arguments

Pass each argument separately, and do file work in Python. Facere runs commands without a shell, so `fac.run("mkdir -p build")` looks for a program named `mkdir -p build`. Reaching for a shell instead, through `os.system` or `shell=True`, ties the build to one platform's shell, keeps the programs out of the fingerprint, and hides the paths from the undeclared-path check.

```python
# Bad: needs a POSIX shell, and Facere sees neither gcc nor the paths
subprocess.run(f"mkdir -p {obj_dir} && gcc -c {src} -o {obj}", shell=True, check=True)
```

```python
# Good
os.makedirs(obj_dir, exist_ok=True)
fac.run(CC, "-c", src, "-o", obj)
```

Give each path its own argument, or put it after `=`. `fac.run` checks each argument and the parts of a flag split at `=` and `,`, so a path glued to its flag, as in `-Tsrc/link.ld`, escapes the check, and editing an undeclared linker script never relinks the program.

## Determinism

Make a rerun write identical bytes. An output that differs on every rerun makes everything downstream rerun every time.

- **Listings.** Sort `os.listdir`, `os.scandir`, `os.walk`, and `glob.glob`, which return filesystem order. `fac.sources` is already sorted.
- **Sets.** Never build a list, a command, or file content by iterating a set: a set of strings iterates in a different order in every process. A list built from one at module level changes the rule's fingerprint, so it reruns every time. Use `sorted()`, or a `dict` for insertion order.
- **Archives.** Avoid `shutil.make_archive`, which records file mtimes, the current user, and the time. Write archives with `zipfile` and `tarfile`, with sorted members, fixed times, owners, and modes, and gzip's `mtime=0`. From the command line, use GNU `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner`, then `gzip -n`.

## Scratch files

Name every scratch file after one of the rule's own outputs, since output paths are unique. Facere cannot see writes: two rules writing one undeclared path, such as a shared depfile name, race under `-j` and the run still passes. Never read another rule's scratch file, since that orders nothing.

Once a tool succeeds, report what it read through `fac.add_inputs`, or editing a header it read reruns nothing. For C, `fac.c.makefile_deps` reads that list from the compiler's depfile.

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

Point caches that tools drop beside the sources into the output directory, or turn them off, or `fac.sources` globs pick them up as inputs: `PYTHONPYCACHEPREFIX` for `__pycache__`, and `--cache-dir` where a tool offers one. Hidden caches, such as `.pytest_cache`, need nothing, since globs skip hidden paths unless the glob names them.

## Tests and deploys

Make tests and deploys tasks, and build what they run in rules. A test's verdict depends on more than Facere sees, so a test written as a rule producing a log reports a cached pass long after the code broke.

```python
# Bad: a passing log is taken as proof until an input changes
@fac.rule
def tests(program: fac.Input = TEST_BINARY, log: fac.Output = fac.out("tests.log")):
    fac.run(program, stdout=log)
```

```python
# Good
@fac.task
def tests(programs: list[fac.Input] = TEST_BINARIES):
    for program in programs:
        fac.run(program)
```

Never make a rule input a file a task writes. That file counts as a source, so the rule fails on a fresh clone and is never ordered after the task.

## Module-level code

Run no probe and read no rule output at module level, since it runs on every invocation, `--list` and `--check` included. A rule's output read there holds the previous run's content, so the build lags one run behind, and fails on a fresh clone. Move a probe into a rule whose output its consumers input, or drop it, since Facere already hashes every program `fac.run` launches.

```python
# Bad: a spawn on every invocation
GCC_VERSION = subprocess.run(
    ["gcc", "-dumpversion"], capture_output=True, text=True, check=True
).stdout
```

```python
# Good: runs only when gcc changes, and consumers rerun only when its version does
@fac.rule
def gcc_version(path: fac.Output = fac.out("gcc-version.txt")):
    version = fac.run("gcc", "-dumpversion", quiet=True).strip()
    assert int(version.split(".")[0]) >= 14, f"gcc 14 or newer required, found {version}"
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(f"{version}\n")
```

The assertion makes the rule a version check as well. A program missing from `PATH` fails only a rule that must execute, so a project that wants a missing gcc to fail every invocation needing `gcc_version` marks it `always=True`, at the cost of one spawn per invocation.

## Network access

Pin every download by passing `sha256=` to `fac.fetch`, or mark data that moves `always=True`. An unpinned download in an ordinary rule runs only when Facere would rebuild its output anyway, so the data silently stays old. An `always=True` rule fetches on every run, and its consumers still rerun only when the bytes change.

## Generated file names

Declare every file a generator writes, deriving the names at collection, as from each spec's name, or passing the tool a flag that fixes them. A file a generator names for itself is an undeclared scratch file, which a rule can read without being ordered after the generator. Where the names cannot be known, declare the directory as one output and consume it in one rule.

```python
# Good: protoc's names follow from each spec's
GENERATED = [(spec, fac.out(spec, ".pb.cc"), fac.out(spec, ".pb.h")) for spec in PROTOS]


@fac.rule(each=GENERATED)
def proto(spec: fac.Input, source: fac.Output, header: fac.Output):
    fac.run("protoc", f"--cpp_out={fac.out(fac.from_root('.'))}", spec)
```

## Rule granularity

Write one rule per independent output and one per tool invocation. Facere reruns a rule whole, so batching independent files reruns them all when one changes. Splitting one invocation is worse: several rules each declaring one of its files all write every file, an undeclared race under `-j`. Batch only tools with a heavy startup, such as a JVM or Nuitka.

## Orphaned outputs

Delete the old file yourself when you rename or remove an output, since Facere leaves it on disk. An orphan does harm once something lists its directory: a linker search path finds an old `libfoo.a`, or `glob(f"{dist}/*")` uploads an old wheel. Input declared paths rather than listing a directory.

## Minimum version

Omit `fac.minimum_version` unless the `fac.py` may meet a Facere older than the latest release, as on machines that upgrade Facere on a schedule of their own. There, call it at the top of `fac.py` with the oldest release whose behavior the file relies on, as in `fac.minimum_version("0.2")`, so an older Facere fails at once, naming how to upgrade, rather than misread the file.
