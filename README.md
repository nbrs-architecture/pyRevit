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

The `Sync core from upstream` workflow runs weekly (and can be run manually from
the Actions tab). It opens a pull request with core-only updates. Review and
merge it — it never touches `extensions/pyRevitTools.extension/`.
