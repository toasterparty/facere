# Releasing

Run `fac bump -- major`, `minor`, or `patch`, commit, then push a matching `v<version>` tag, such as `v0.2.0`. The tag runs the `Release` workflow, which tests and then publishes to PyPI through [trusted publishing](https://docs.pypi.org/trusted-publishers/) from the `pypi` environment. The workflow publishes `VERSION` whatever the tag says, so check the two match before pushing. The workflow builds with `MINIMUM_FACERE` from the root `fac.py`, an earlier release, so raise it only once the new release is on PyPI and the root `fac.py` needs it.
