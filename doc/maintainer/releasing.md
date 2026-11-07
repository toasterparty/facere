# Releasing

Run the `Release` workflow from `main` and pick a release type. It runs CI, builds the release, pushes the version commit and its tag in one atomic push, then publishes to PyPI through [trusted publishing](https://docs.pypi.org/trusted-publishers/). To try the build step locally, run `fac build_release -- Minor`: it builds in a scratch clone and writes only under `build/`.

| Failure | Remote state | Recovery |
| ------- | ------------ | -------- |
| Before `push` | Unchanged | Run it again |
| `push` rejected because the branch moved | Unchanged | Run it again. "Re-run failed jobs" reuses the old commit and is rejected again |
| `publish` | Tag exists, PyPI empty or partial | "Re-run failed jobs", which skips files already uploaded |
| A bad release shipped | On PyPI, which never reuses a filename | Yank it on PyPI, then release a `Patch` |

## 1.0

`validate_release` in `release.py` refuses any version from `1.0.0` up, since after a stray `Major` `main` could release nothing below 1.0. When 1.0 is due, delete that check and its test, then release `Major`.

## Hotfixes

Fix `main` first if the bug is there too, then branch from the tag, apply the fix, push, and run `Patch` from the branch, the only type it allows:

```sh
git checkout v1.2.0
git checkout -b hotfix/v1.2
git cherry-pick <fix>
git push -u origin hotfix/v1.2
```

The branch keeps its own version commits and never merges back. A run uses the workflow file on its branch, so an old branch may need workflow fixes cherry-picked to it.

## Repository settings

Create both environments before the first run, since a run creates a missing one unprotected.

- **Merges:** squash only, with the PR title as the commit title.
- **Environments:** `release` and `pypi`, each deploying only from `main` and `hotfix/*`. That policy is the real limit on where releases run, since a branch can edit its own copy of the workflow.
- **PyPI:** a trusted publisher naming `release.yml` and the `pypi` environment.
- **Deploy key:** a key with write access, its private half stored as `RELEASE_DEPLOY_KEY` in the `release` environment.
- **`v*` tag ruleset:** restrict creation, update, and deletion, with the deploy key on the bypass list.
- **`main` ruleset:** block force-push and deletion, with the deploy key on the bypass list. From 1.0, also apply it to `hotfix/*`, and require a pull request and the `ci-pass` check. Leave "require branches to be up to date" off, or every release makes each open pull request stale.
