# Example: a sum from downloaded data

> **Status:** planned. This example uses `fac.fetch` and `@fac.rule(always=True)`, which no release supports yet, so it does not run on the current release.

The use case Facere must keep simple, beside the [C server and client](../c-server-client/README.md) that tests the hard ones. `https://example.com/data.json` holds integer keys `a` and `b`, and `build/out.txt` must hold their sum, downloaded with nothing but Python. The design is in [Design](../../maintainer/design/README.md).

[`fac.py`](./fac.py) has two rules connected by a path, and a task. The data moves, so `data` fetches without a pin and runs on every invocation, while `sum_` re-executes only when the downloaded bytes differ. `fac.fetch.file` asks the server whether the file changed since the last download, as `wget -N` does, fails on an HTTP error, and writes the file only once it has arrived whole. `sum_` answers to `fac sum`, the trailing underscore keeping the built-in `sum` unshadowed. Every output lies in `build/`, so `clean` needs no paths of its own.

## Runs

| Action | Executes | Why |
|---|---|---|
| `fac` | `data`, `sum` | Nothing is recorded yet |
| `fac` | `data` | `data` always runs, the server answers that the file has not changed, and `sum` stays up to date |
| The server's data changes, then `fac` | `data`, `sum` | The downloaded bytes differ |
| Edit `build/out.txt`, then `fac` | `data`, `sum` | An output no longer matches its recorded hash |
| The server returns 404, or the network is down | `data`, failing with the download's error | Its record is cleared, so `sum` keeps its last result and the next run tries again |
| `fac clean` | `clean` | Deleting `build/` removes every output and forgets every record |
| `fac clean sum` | `clean`, then `data` and `sum` | Names run in order, and the first left nothing recorded |

## Rough edges

- **A proxy** reaches the download from Facere's own environment, unfingerprinted, under the one exception to configuring nothing through the environment.
