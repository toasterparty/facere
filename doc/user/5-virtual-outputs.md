# Virtual outputs

*(planned)* An output need not be a file of its own. Where many small results belong together, such as the rows of one table or the pages of a CMS, Facere will track each one separately however they are stored, so a change to one executes only its own rules. A project with one file per output needs none of this.

A store keeps many outputs in one place of your choosing, such as one file or an HTTP REST API, while Facere still tracks each one separately. Each output it holds is a virtual output, named `fac.Virtual(store, key)` and reaching its key as `.key`, which a rule declares with `fac.VirtualOutput` to write it or `fac.VirtualInput` to read it. In the recipe, `fac.write(virtual_output, value)` sets a virtual output, and a recipe must set every virtual output it declares, while `fac.read(virtual_input)` returns a virtual output the rule inputs. Facere writes to the store once recipes succeed, in one `update` per batch however many virtual outputs changed, and re-executes only the rules whose virtual outputs changed. Two rules cannot output one virtual output. Keys and values are values Facere can hash, such as strings, numbers, and tuples.

For a store kept in one file, subclass `fac.FileStore`, constructed with the file's path, and give the file's format as two methods:

```python
class Rows(fac.FileStore):
    def read(self):
        rows = {}
        for line in fac.read_text(self.path).splitlines():
            row, _, text = line.partition(" ")
            rows[int(row)] = text
        return rows

    def write(self, rows):
        fac.write_text(self.path, "".join(f"{row} {text}\n" for row, text in rows.items()))


ROWS = Rows(fac.out("rows.txt"))
GREETING_RULES = [
    {"output": fac.Virtual(ROWS, row), "name": name} for row, name in enumerate(NAMES)
]


@fac.rule(each=GREETING_RULES)
def greeting(output: fac.VirtualOutput, name: str):
    fac.write(output, f"hello, {name}")
```

`read()` returns every virtual output the file holds as a dict from key to value, and `write(outputs)` replaces the file with exactly the virtual outputs given. A missing file, or one whose `read` raises, holds no virtual outputs, so `read` need not handle either. A store with nothing stale costs one stat of its file, however many virtual outputs it holds, and `fac build/rows.txt` builds every rule writing to it.

Any other store is a class with three methods, whose attributes, such as a URL, say where it lies:

| Method | Returns or does |
| --- | --- |
| `stamp()` | A cheap token that changes whenever any virtual output does, such as a collection's ETag, or `None` when there is none |
| `read(keys)` | A dict holding the virtual outputs among `keys` the store holds. A key it leaves out is a missing virtual output, and it may return more virtual outputs than asked for |
| `update(changed)` | Writes the virtual outputs in the dict `changed`, leaving the rest alone |

```python
class Pages:
    def __init__(self, url):
        self.url = url

    def stamp(self):
        with urllib.request.urlopen(urllib.request.Request(self.url, method="HEAD")) as response:
            return response.headers["ETag"]

    def read(self, keys):
        with urllib.request.urlopen(self.url) as response:
            return json.load(response)

    def update(self, changed):
        for slug, html in changed.items():
            request = urllib.request.Request(f"{self.url}/{slug}", html.encode(), method="PUT")
            urllib.request.urlopen(request).close()
```

Facere calls a store's methods one at a time, with the root as the working directory, and only for targets that need its virtual outputs, so building only local files never reaches the network. It takes the stamp once per build before writing and reads only when the stamp changed, then reads back what it wrote to check that each virtual output arrived as written. Any other store that raises fails the build. A change to a store's code re-executes every rule writing to it, and a store with other attributes, such as another URL, is another store, so every rule writing to it re-executes. A method that changes an attribute fails the invocation. A `FileStore` is identified by its path alone.

[<- Multiple `fac.py` files](./4-multiple-fac-py.md) | [Debugging and tracing ->](./6-debugging.md)
