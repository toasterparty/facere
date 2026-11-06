# Fetching

`facere.fetch` provides `file(path, url, sha256=None, when=When.NEWER)`, with the enum `When` naming when an unpinned file is fetched again, and `archive(path, url, sha256, strip_components=0)`, for tarballs and zip files. Both are plain functions a recipe calls, so they touch the network only when the calling rule executes, and their URL and hash join that rule's fingerprint through its code or its values. Each writes its file only once it has arrived whole and matched its hash, if given one.

A fetch given a hash is pinned, and pins are immutable, since resolving a moving ref would put a network call in every invocation and break offline use. An unpinned `file` is for data that moves.

## `file`

`file` behaves like wget. A file already matching a given hash is never fetched again. Without a hash, `When.NEWER`, the default, sends the ETag and Last-Modified the server gave at the last success, kept through `fac.save()`, and keeps the file when the server answers that it has not changed, as `wget -N` does. A server sending neither is fetched in full every time. `When.MISSING` skips the request when the file exists and came from the same URL, as `wget -nc` does. Downloads honour the standard proxy and certificate variables of Facere's environment, unfingerprinted, as every command does.

## `archive`

`archive` verifies the archive's hash, deletes the directory before unpacking, since Facere leaves an existing output in place and a new archive may lack files the old one had, and checks every extracted file against the archive's own listing before it returns, so a truncated extraction fails. The downloaded archive stays in the output directory, at `fac.out(path)` with the archive's own extension, so rebuilding a damaged tree unpacks it again without the network, and every extracted file's hash goes to `fac.save()`, so a re-execute that finds the tree intact unpacks nothing. Deleting the output directory forgets both, and the next invocation downloads again. A project wanting a cache that outlives the output directory builds it with rules of its own. A fetched directory therefore holds nothing but the archive's files: another rule's output inside it would be deleted, which Facere reports when it happens between that rule and a rule reading its output.

A rule calling `archive` may declare only the files its consumers read, as any [output](../fingerprints.md#outputs) may.

GitHub generates tag archives on demand and has changed their bytes before, which breaks every pin at once. A release asset or a mirror makes a sturdier pin where one exists.
