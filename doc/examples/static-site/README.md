# Example: a static site

Markdown pages rendered to HTML and gathered into one directory, ready to serve. Each page is one rule through `each=`, `fac.sources` finds the pages, and [`tools/render.py`](./tools/render.py) is a shared module, whose code Facere fingerprints as it does the `fac.py`'s own. The example needs nothing but Python.

| Action | Executes | Why |
|---|---|---|
| `fac` | 2 pages, `index`, `site` | Nothing is recorded yet |
| `fac` | none | Every fingerprint matches |
| Edit a paragraph in `pages/about.md`, then `fac` | about's page, `index`, `site` | `index` inputs every source, though its output comes out the same |
| Edit `template.html`, then `fac` | 2 pages, `index`, `site` | The pages and `index` input the template |
| Change `SITE_NAME`, then `fac` | 2 pages, `index`, `site` | A module constant a recipe reads joins its fingerprint |
| Add a comment to `tools/render.py`, then `fac` | none | Fingerprints hash the syntax tree, which holds no comments |
| Change the HTML `render_body` writes, then `fac` | 2 pages, `site` | Only the page rules reach `render_body`, and `index` stays up to date |
| Add `pages/news.md`, then `fac` | news's page, `index`, `site` | The glob lists a new page |
| Delete `build/site`, then `fac` | `site` | An output no longer matches its recorded hash |
| `fac serve -- 8000` | whatever is stale, then the server | A task executes live, after the rules it needs, until you stop it |
| Raise `fac.minimum_version` past the running Facere, then `fac` | none, failing, naming how to upgrade | A project declares the oldest Facere it needs |
| `fac clean`, then `fac` | `clean`, then 4 rules | Deleting `build/` forgets every record |
