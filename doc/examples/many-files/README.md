# Example: many rules

One rule function, `row`, defines `ROW_COUNT` rules, 1500, each writing `build/rows/NNNN.txt` from its revision. The revisions live in one file, `table.txt`, read while `fac.py` loads. Each rule receives only its own revision as a value, and the table is not an input, so editing a row makes that row's rule stale and no other. `fac row` builds all of them, since a name covers every rule its function defines. The example needs nothing but Python, and exists to watch how Facere reports a build with many rules.

| Action | Executes | Why |
|---|---|---|
| `fac` | 1500 rules | Nothing is recorded yet, and a missing table means every revision is 0 |
| `fac` | none | Every fingerprint matches, and Facere reports that there was no work to do |
| `fac invalidate`, then `fac` | `invalidate`, then 1500 rules | `invalidate` raises every revision in the table, so every rule sees a new value |
| `fac invalidate -- --count 750`, then `fac` | `invalidate`, then 750 rules | `--count` sets how many of the first rows change |
| `fac clean`, then `fac` | `clean`, then 1500 rules | Deleting `build/` forgets every record, and the table stays |
| Delete `build/rows/0007.txt`, then `fac` | 1 rule | An output no longer matches its recorded hash |
