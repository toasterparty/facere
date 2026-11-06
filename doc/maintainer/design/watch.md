# Watch mode

Watch mode follows 1.0. `fac --watch NAME...` runs until interrupted and serves two goals: building on save in any editor, and live tasks such as a test run or a dev server that restart on a change. Lower latency than a fresh invocation is not a goal, and neither is editor diagnostics integration.

## Requirements

- Watch mode MUST build the given names, then build them again whenever a file the previous cycle read, or a directory it listed, changes content.
- Every name given to watch mode is something to build or a task to start. A change MUST restart every named task once the names before it are built. A task not named MUST NOT be stopped or restarted by watch mode.
- Watch mode MUST NOT start a cycle for a change that leaves every observed file's content and every listed directory's entries as they were, or for an output Facere itself wrote.
- Watch mode MUST behave identically on Linux and Windows. It MUST NOT miss a change on a file system that reports none, though it MAY notice the change later.
- Each cycle MUST end with a fixed line an editor can match. The 3-line budget for Facere's own output does not count it.

## Design

- **Supervisor.** `fac --watch app test` starts a supervisor that runs no collection and holds no lock. Each cycle, it spawns a fresh `fac app test` child, inheriting the terminal, and waits for a change. A loop calling `fac.main()` in one process cannot work: a task's recipe is Python in a worker thread, and Python cannot kill a thread, so a recipe that catches the error from its killed command, or serves from Python itself, could never be restarted. Django's autoreloader, iBazel, watchexec, and `deno --watch` restart processes for the same reason. A fresh process costs about 46 ms of interpreter start and imports per cycle. Every cycle collects again, so an edit to a `fac.py` or a shared module takes effect on the next one.
- **Triggers.** A cycle starts when something the previous cycle observed changes: a `fac.py` or shared module it loaded, a directory it listed, or a file it hashed, task inputs included. Nothing else does: not a store other than a `FileStore`, whose file is observed as any file, not a hidden path, a file no cycle read, or a scratch file in the output directory. The supervisor confirms a change as the hash cache does, rehashing a file whose size, mtime, ctime, or inode moved and relisting a directory whose mtime moved. It counts the change only when content or entries differ from the record, so saving an unchanged buffer, `touch`, and an editor's atomic-save temporaries start nothing. A declared output whose content matches its record is Facere's own write and starts nothing, while one edited by hand starts a cycle that rebuilds it. A writer that is not idempotent, such as a task stamping the time into a globbed file, still loops, so each cycle prints the paths that started it, as in `fac: change in src/main.c, lib/fac.py`, and a narrower glob fixes the loop.
- **Detection.** The supervisor polls the observed set, since inotify misses changes another machine makes on a network file system, and under WSL2 a Linux watcher sees no edit a Windows application makes on a Windows drive. A sweep costs about 20 ms on the N100 for the 7000-file benchmark, about 4% of one core at a 500 ms interval. Native events, inotify and `ReadDirectoryChangesW` through `ctypes`, can be added later as wake-up hints over a slower safety sweep, if polling's idle cost is measured to matter, while macOS keeps polling.
- **Debounce.** After the first confirmed change, the supervisor waits until 100 ms pass with no other, so Save All and a formatter's rewrite after a save start one cycle. The quiet period takes no flag. A write landing after a cycle has started starts another, which skips every rule the first one finished.
- **A change during a cycle.** The supervisor sends the child the graceful stop, so a user saving every 20 s during a 60 s build still gets one finished. The next cycle rebuilds what is stale and starts the named tasks again.
- **Tasks the user owns.** A server that reloads itself, such as Vite, runs as a task in its own `fac` and calls `fac.give_lock()`, as in `fac serve` in one terminal and `fac --watch app` in another.
- **Terminal.** The child has the terminal, so tasks print live and read stdin, and on Linux and macOS Ctrl-C reaches the whole foreground process group. The supervisor reads no keys and never clears the screen.

## What 1.0 must already provide

- the lock the kernel releases, so a killed child never leaves one behind
- the graceful stop, which is the supervisor's only request to its child
- one audit hook per process
- output an editor can parse

Watch mode also needs the set of paths a cycle observed. The state already holds the hashed files and the cached directory listings. Each task's declared inputs, and which directories collection listed, join it when watch mode ships.

## Windows and editors

- **Ctrl-C on Windows.** The supervisor can send `CTRL_BREAK_EVENT` only to a child started with `CREATE_NEW_PROCESS_GROUP`, and that flag also disables Ctrl-C in the child and everything it starts. The child therefore re-enables Ctrl-C through `SetConsoleCtrlHandler(None, False)` at startup, so Ctrl-C behaves as on Linux and macOS.
- **Cycle markers.** A VS Code background task tracks a watcher through a `beginsPattern` and an `endsPattern`, as `tsc --watch` prints `File change detected. Starting incremental compilation...`. The `fac: change in ...` line begins a cycle, and the fixed closing line ends it.
