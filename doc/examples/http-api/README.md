# Example: files and an HTTP REST API

> **Status:** planned. This example uses `fac.Virtual`, `fac.read`, and `fac.write`, which no release supports yet, so it does not run on the current release.

Markdown pages are rendered to local previews, each preview is published to a CMS as one page, and `build/titles.txt` lists the title of every page the CMS holds. `Pages` is a [store](../../user/5-virtual-outputs.md) whose virtual outputs are the CMS's pages, written with one PUT each and checked with one HEAD request for the collection's ETag. The example needs nothing but Python: [`tools/fake_cms.py`](./tools/fake_cms.py) stands in for the CMS, so start `python doc/examples/http-api/tools/fake_cms.py` in another terminal before running `fac`.

```
fac.py
pages/about.md
pages/contact.md
pages/index.md
tools/fake_cms.py    the CMS, in memory, at the URL fac.py names
```

| Action | Executes | Why |
|---|---|---|
| `fac` | 3 previews, 3 pages, `titles` | Nothing is recorded yet |
| `fac` | none | The CMS's ETag matches the one recorded with the pages' digests, so Facere reads no page |
| Edit the text of `pages/about.md`, then `fac` | about's preview and page, `titles` | `titles` inputs every page, and only about's changed |
| Change the about page on the CMS, as with `curl -X PUT --data-binary '<h1>x</h1>' http://127.0.0.1:8000/pages/about`, then `fac` | about's page | That virtual output no longer matches its record, and publishing it again restores the value `titles` recorded |
| Add `pages/news.md`, then `fac` | news's preview and page, `titles` | The glob lists a new page, and `titles` gains an input |
| Delete `pages/contact.md`, then `fac` | `titles` | `titles` loses an input, and the CMS keeps the contact page, since Facere deletes nothing it no longer tracks |
| Stop the CMS, then `fac preview` | none | No preview needs the CMS, so Facere sends it no request |
| Stop the CMS, then `fac` | none, failing | The HEAD request fails, and Facere cannot tell whether a page is stale |
| `fac clean`, then `fac` | `clean`, then 7 rules | Deleting `build/` forgets every record, while the CMS keeps its pages |

## Rough edges

- **One PUT per page.** `update` receives every changed page at once, so a CMS with a bulk endpoint takes one request for any number of pages.
- **A CMS with no collection ETag** needs `stamp` to return `None`, and every `fac` then reads every page.
