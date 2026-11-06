# Example: many rules, one file

> **Status:** planned. This example uses `fac.FileStore`, `fac.Virtual`, and `fac.write`, which no release supports yet, so it does not run on the current release.

The rules of [many files](../many-files/README.md), each writing one line of `build/rows.txt` instead of a file of its own. `Rows`, a [store](../../user/5-virtual-outputs.md) kept in one file, gives the file's format as a `read` and a `write`, and each rule's virtual output is its row. A recipe only hands Facere its row, so a build writes the file once rather than 1500 times, and a build with nothing stale costs one stat. The example needs nothing but Python.

| Action | Executes | Why |
|---|---|---|
| `fac` | 1500 rules | Nothing is recorded yet, and a missing table means every revision is 0 |
| `fac` | none | The file's stat matches its record, so Facere reads no row |
| `fac invalidate`, then `fac` | `invalidate`, then 1500 rules | Every rule sees a new value |
| `fac invalidate -- --count 750`, then `fac` | `invalidate`, then 750 rules | Only the first 750 revisions change, and `write` rewrites the other lines unchanged |
| `fac clean`, then `fac` | `clean`, then 1500 rules | Deleting `build/` forgets every record, and the table stays |
| Edit line `0007` of `build/rows.txt`, then `fac` | 1 rule | That virtual output no longer matches its recorded digest, and the write restores the line |
| Delete `build/rows.txt`, then `fac` | 1500 rules | A missing file holds no virtual outputs |
| Change the line format in `Rows.write`, then `fac` | 1500 rules | A store's code joins the fingerprint of every rule writing to it |
| Edit `invalidate`, then `fac` | none | A store's fingerprint holds its class's code, never its whole module |
