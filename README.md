# pyRevit (NBRS fork)

Company-maintained pyRevit deployment. This fork tracks the upstream pyRevit
**core** (engine, libraries, and the `pyRevit` ribbon tab) and keeps a single
in-house extension: **pyRevitTools**.

## What lives here

| Path | Owned by | Updated by |
|------|----------|------------|
| `pyrevitlib/`, `site-packages/` | upstream pyRevit | `Sync core from upstream` workflow |
| `extensions/pyRevitCore.extension/` | upstream pyRevit | `Sync core from upstream` workflow |
| `extensions/pyRevitTools.extension/` | **us** | team PRs on the `pyrevittools` branch |
| `pyRevitfile`, `extensions/extensions.json` | upstream pyRevit | `Sync core from upstream` workflow |

`bin/` is not stored here — `pyrevit clone` downloads matching binaries automatically.

## Editing our tools

1. Work on the `pyrevittools` branch.
2. Make your changes under `extensions/pyRevitTools.extension/`.
3. Note the change in `PYREVITTOOLS_CHANGES.md`.
4. Open a pull request to `master` and get a review.
5. After merge, machines update with:

```
pyrevit clones update OrgClone --skip-bin
```

## Syncing with upstream

The `Sync core from upstream` workflow runs a quarterly check (and can be run
manually from the Actions tab). A scheduled check only opens an issue when
upstream has new core changes — it never auto-pushes. To actually sync, run the
workflow manually with **push** enabled to commit and push core changes directly
to `master`. Pushing requires your GitHub user to be listed in the
`SYNC_ALLOWED_ACTORS` repo variable (a JSON array, e.g. `["user1","user2"]`).
It never touches `extensions/pyRevitTools.extension/`.
