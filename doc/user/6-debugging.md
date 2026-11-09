# Debugging and tracing

## See what ran

`-v` *(0.2)* prints each command as one string before it runs, after `fac.run` has flattened its arguments, so you can paste it into a shell:

```
$ fac -v
/usr/bin/python3 tools/sitemap.py https://example.com/ index.html about.html
Finished in 59ms. Executed 1 rule.
```

`-v` leaves out `cwd=`, `env=`, and redirections, so print those from the recipe where they matter.

## Read a failure

A failed command prints first, followed by its unaltered output, then the rule, at its line in `fac.py`:

```
fac: command exited with status 1: /usr/bin/python3 tools/sitemap.py https://example.com/ index.html about.html
sitemap.py: no base URL given
fac.py:60:2: error: rule 'sitemap' (build/pages/sitemap.txt) failed
```

A Python exception in a recipe prints its traceback in place of the command. A mistake in the `fac.py` itself, such as two rules outputting one path, a dependency cycle, or an unannotated path, fails before any recipe executes, naming the lines involved.

## Step through a recipe

Recipes are ordinary Python running inside `fac`, so `print` and `breakpoint()` work in them. Adding one changes the recipe's code, so the rule executes once more. A `print` at module level runs on every invocation, as the file loads.

## Work out why a rule did or did not execute

*(planned)* `fac -v` will name why each rule executes, `fac --check` will report what is stale without executing anything, and `fac --list` will show every rule and task. Until then:

| Symptom | Look at |
| --- | --- |
| A rule never executes after a change | Whether the changed thing is declared. [Hidden inputs](./7-best-practices.md#hidden-inputs) lists what stays out of every fingerprint |
| A rule executes on every invocation | A module-level value that differs per run, such as the time or a `list` built from a `set` |
| Everything downstream executes | An output whose bytes differ on every execution, as [identical outputs](./7-best-practices.md#identical-outputs) describes |
| A rule fails on a fresh clone only | An input some other rule's recipe leaves behind undeclared, or a rule output read while `fac.py` loads |

To execute one rule again, delete its output, or delete the output directory to execute them all. Facere keeps its state there, so losing it costs only rebuilds.

## See where the time goes

*(planned)* `fac --timings` will print interpreter start, collection, hashing, and each rule's duration, along with the critical path.

[<- Virtual outputs](./5-virtual-outputs.md) | [Best practices ->](./7-best-practices.md)
