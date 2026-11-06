# Design

How Facere meets its [requirements](../requirements.md), and why. Much of it is not yet implemented. The code is the authority on what exists today, and where it contradicts a design here, raise the conflict rather than following either silently. Key words in a design's own requirements are as defined in the requirements.

- [The `fac.py` interface](./fac-py.md) - before adding or changing anything a `fac.py` calls, declares, or imports
- [Names and scopes](./names.md) - before changing scopes, names, defaults, groups, or how command-line targets resolve
- [Command line](./command-line.md) - before adding or changing a flag
- [Collection](./collection.md) - before changing how `fac.py` files are found, loaded, or validated
- [Fingerprints and checks](./fingerprints.md) - before changing what makes a rule stale, added inputs, or the checks on undeclared paths and writes
- [Stores and virtual outputs](./stores.md) - before changing how rules output or input anything but a file, or how a store is read, written, or checked
- [Execution](./execution.md) - before changing how commands run, their environment, scheduling, failure, or Facere's output
- [State and lock](./state.md) - before changing what Facere records between invocations, or how concurrent invocations wait
- [Distribution](./distribution.md) - before changing packaging, installation, compatibility, the shipped docs, or the repository's layout
- [Performance](./performance.md) - before optimizing, or adding work to an invocation with nothing stale
- [Extensions](./extensions/README.md) - before writing or changing an extension Facere ships
- [Watch mode](./watch.md) - before implementing watch mode, or changing the lock, the graceful stop, or the audit hook it relies on
