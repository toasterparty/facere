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

A Python exception in a recipe prints its traceback in place of the command. *(0.4)* The invocation then ends on a line starting with `Failed`, after the rules already executing finish, and no other rule starts. `fac -k` instead keeps building everything that does not depend on what failed, printing each failure as it happens. A mistake in the `fac.py` itself, such as two rules outputting one path, a dependency cycle, or an unannotated path, fails before any recipe executes, naming the lines involved.

## Step through a recipe

Recipes are ordinary Python running inside `fac`, so `print` and `breakpoint()` work in them. Adding one changes the recipe's code, so the rule executes once more. *(0.4)* A rule's prints appear once it finishes, but from `breakpoint()` on its recipe holds the terminal until it returns, as a command running `fac.Console.LIVE` does: what it printed so far appears first, the debugger prompts at once, and other rules keep executing while their output waits. A task prints as it runs, so `breakpoint()` works there too. A `print` at module level runs on every invocation, as the file loads.

## Work out why a rule did or did not execute

*(planned)* `fac -v` will name why each rule executes, `fac --check` will report what is stale without executing anything, and `fac --list` will show every rule and task. Until then:

| Symptom | Look at |
| --- | --- |
| A rule never executes after a change | Whether the changed thing is declared. [Hidden inputs](./7-best-practices.md#hidden-inputs) lists what stays out of every fingerprint |
| A rule executes on every invocation | A module-level value that differs per run, such as the time or a `list` built from a `set`. *(0.4)* A tool that changes its own input, or writes a file outside the output directory that its recipe reports: from the second such execution `fac` warns that the rule `stays stale`, naming the file |
| A rule executes once more after a build | *(0.4)* An input saved while its recipe executed, or a tool that installed files it then read, as `uvx` does on its first run |
| Everything downstream executes | An output whose bytes differ on every execution, as [identical outputs](./7-best-practices.md#identical-outputs) describes |
| A rule fails on a fresh clone only | An input some other rule's recipe leaves behind undeclared, or a rule output read while `fac.py` loads |

To execute one rule again, delete its output, or delete the output directory to execute them all. Facere keeps its state there, so losing it costs only rebuilds.

## See where the time goes

*(planned)* `fac --timings` will print interpreter start, collection, hashing, and each rule's duration, along with the critical path.

[<- Virtual outputs](./5-virtual-outputs.md) | [Best practices ->](./7-best-practices.md)
