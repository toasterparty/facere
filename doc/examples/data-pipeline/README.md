# Example: a data pipeline

Sales figures from each region are cleaned, totaled, and written up, with each step a separate program that knows nothing of Facere. [`fac.py`](./fac.py) passes files to them through `stdin=`, `stdout=`, and `stderr=`, a setting through `env=`, a working directory through `cwd=`, and `quiet=True` to a command whose output it reads back. Each rule inputs the tool it runs, so editing one executes the rules that use it. The example needs nothing but Python.

| Action | Executes | Why |
|---|---|---|
| `fac` | 2 `clean_data`, `total`, `report`, `checksums` | Nothing is recorded yet |
| `fac` | none | Every fingerprint matches |
| Add a row to `data/south.csv`, then `fac` | south's `clean_data`, `total`, `report`, `checksums` | The new row changes every output downstream |
| Add a row with a bad amount to `data/north.csv`, then `fac` | north's `clean_data` | Only its rejects changed, and its cleaned table came out the same |
| Change `CURRENCY`, then `fac` | `total`, `report`, `checksums` | `total` reads it, and its summary changes |
| Change `TITLE`, then `fac` | `report`, `checksums` | `report` reads it through its default, and the totals stay |
| Edit `tools/table.py`, then `fac` | `report`, then `checksums` if the report changed | The tool is an input of `report` |
| `fac show` | whatever is stale, then `show` | A task always executes |
| `fac clean`, then `fac` | `clean`, then 5 rules | Deleting `build/` forgets every record |
