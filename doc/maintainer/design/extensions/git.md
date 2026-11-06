# git repositories

`facere.git` serves dependencies kept as git repositories rather than archives, such as one a project would otherwise vendor as a submodule. A project's own submodules belong to git, whose index pins them, and stay out of scope: `clone` replaces a submodule rather than driving one.

## Requirements

- A pinned checkout MUST NOT touch the network while its tree is intact, or while the commit it needs is already stored in the output directory.
- A checkout MUST hold no `.git` inside its tree, so a git command run there, an editor's background `git status` included, changes nothing Facere tracks.
- A tag or branch MUST resolve at most once per execution of the calling rule.

## API

`clone(path, url, ref, commit=None, recursive=False)` is a plain function a recipe calls, as `facere.fetch`'s are, so its arguments join the calling rule's fingerprint. It writes the tree of `ref` at `path`, root-relative like every path a recipe passes, so a recipe derives it from its parameters.

The repository itself lives in the output directory, at `fac.out(path)` with `.git` appended, and the tree is checked out from it with `--git-dir` and `--work-tree`, so the tree holds only the commit's files. Like `fetch.archive`, it deletes the tree before checking out, since a new commit may lack files the old one had, and a damaged tree is restored from the stored repository without the network. Deleting the output directory forgets the repository, and the next invocation clones again, shallow.

With `commit`, the full hash, the checkout is pinned. When `ref` is a tag, fetching it also resolves the tag on the remote and fails, naming both hashes, when they differ, since a tag can be moved. Without `commit`, `ref` moves, and the calling rule should be marked `always=True`. Each execution then asks the remote what `ref` names with one round trip, and checks out the commit only when it differs from the last one, which it keeps through `fac.save()`. Its consumers re-execute only when the tree's content changed. Without `always=True`, a moving ref is resolved only when Facere would rebuild the rule's outputs anyway, as with an unpinned `fetch.file`.

Every command runs the `git` on `PATH` with the inherited environment, so an SSH agent and git's own credential helpers work unchanged.

```python
CJSON = "third_party/cjson"
CJSON_COMMIT = "..."  # the full hash v1.7.18 names


@fac.rule
def cjson(files: list[fac.Output] = [f"{CJSON}/cJSON.c", f"{CJSON}/cJSON.h"]):
    fac.git.clone(
        os.path.dirname(files[0]),
        "https://github.com/DaveGamble/cJSON.git",
        "v1.7.18",
        commit=CJSON_COMMIT,
    )


@fac.rule(always=True)
def sdk(header: fac.Output = "third_party/sdk/include/sdk.h"):
    fac.git.clone("third_party/sdk", "https://example.com/sdk.git", "main")
```

A cloned repository that ships its own `fac.py` needs `fac.exclude` in the root `fac.py`, since collection would otherwise find it on the next invocation. Tests clone a local bare repository in `tmp_path`, so they need no network.

## Offline and submodules

A moving ref that cannot be resolved, as offline, fails the calling rule, naming `commit=` as the way to build offline, since keeping the last checkout would report success over a tree that may be behind its remote.

With `recursive=True`, `clone` also checks out every submodule of the cloned repository, recursively, at the commit its parent pins, storing each submodule's repository beside the parent's in the output directory, so the tree still holds no `.git`. A submodule pinned by its parent needs no network while its stored repository holds that commit.
