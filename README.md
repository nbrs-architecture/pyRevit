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

> **Careful:** `pyrevitlib/` is *not* purely upstream-owned.
> `pyrevitlib/pyrevit/revit/db/query.py` carries one fork-local change
> (`get_sheet_tblocks`), and the core sync overwrites whole files rather than
> merging them. A sync that does not re-apply that change reverts it silently.
> See [`CORE_SYNC.md`](./CORE_SYNC.md).

## Editing our tools

1. Work on the `pyrevittools` branch.
2. Make your changes under `extensions/pyRevitTools.extension/`.
3. Note the change in `PYREVITTOOLS_CHANGES.md`.
4. Open a pull request to `master` and get a review.
5. After merge, machines update with:

```
pyrevit clones update NBRS --skip-bin
```

The registered clone is `NBRS` (not `OrgClone`). After a core sync the loader
binaries change too, so drop `--skip-bin` for those machines.

## Syncing with upstream

The `Sync core from upstream` workflow runs quarterly (1 Jan/Apr/Jul/Oct) and can
be run manually from the Actions tab. It overlays the core paths from
`pyrevitlabs/pyRevit` `master` and never touches
`extensions/pyRevitTools.extension/` — but it overwrites whole files elsewhere, so
read [`CORE_SYNC.md`](./CORE_SYNC.md) before merging.

A scheduled run only **detects** changes: it pushes nothing and records the pending
sync (as an issue when Issues are enabled, otherwise in the run's step summary). To
actually land a sync, dispatch the workflow with `push: true`; only actors listed in
the `SYNC_ALLOWED_ACTORS` repository variable may push.
