from __future__ import annotations

import facere as fac


@fac.rule
def optional(source: fac.Input | None = None, out: fac.Output = "build/a"):
    pass


@fac.rule
def undefined(source: Missing = None, out: fac.Output = "build/b"):  # noqa: F821  # ty: ignore[unresolved-reference]
    pass
