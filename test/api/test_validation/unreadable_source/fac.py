import facere as fac

exec("def page(out: fac.Output = 'build/a'):\n    pass\n")
fac.rule(page)  # noqa: F821  # ty: ignore[unresolved-reference]
