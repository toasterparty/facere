# Maintaining Facere

The user documentation in [`../user/`](../user/README.md) is part of the product: a change to Facere's behavior updates it in the same change. Its pages are named `<n>-<name>.md` to sort in reading order, each ending with links to its neighbors, which `test/doc/test_docs.py` checks. Until 1.0 it may describe behavior not yet implemented, so check the code before taking it as a statement of what Facere does today. From 1.0 it describes exactly what the release it ships in does. Facere has no users before 1.0, so until then any change may break any interface, with no migration path, deprecation, or release note. The version markers in the user docs serve the root `fac.py`, which a release runs.

- [Development](./development.md) - to set up a checkout, and before building, testing, or linting Facere
- [uv](./uv.md) - before adding, removing, or upgrading a dependency, or creating a virtual environment
- [Principles](./principles.md) - when a design question has no answer in the requirements
- [Requirements](./requirements.md) - before changing what Facere does
- [Use cases](./use-cases.md) - before changing the interface, to check each stays straightforward
- [Design](./design/README.md) - before implementing a feature or changing how one works
- [Roadmap](./roadmap.md) - when choosing what to build next, or settling an open decision
- [Releasing](./releasing.md) - when cutting a release, or changing the workflows or the repository's GitHub settings
- [`fac.py` style](./fac-py-style.md) - before writing or editing an example `fac.py` or a snippet of one in the user docs
