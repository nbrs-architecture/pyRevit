# Core sync runbook

How this fork takes pyRevit **core** updates from
[pyrevitlabs/pyRevit](https://github.com/pyrevitlabs/pyRevit), and what to watch
out for while doing it.

## Current state

| | Version | Upstream commit |
|---|---|---|
| fork core (on `master`) | `6.5.3.26176+2017` | `b74f72a1` (tag `v6.5.3.26176+2017`) |
| upstream `master` | `7.0.0.26278+2233` | `ccc49398` (tag `v7.0.0.26278+2233`) |

`pyrevitlib/pyrevit/version` is the source of truth for the core version this fork
is carrying; compare it with upstream before assuming a sync is outstanding.

## What the workflow does

`.github/workflows/sync-core.yml` lives on `master` only:

1. fetches `upstream master`;
2. overlays the synced paths — `pyrevitlib`, `site-packages`,
   `extensions/pyRevitCore.extension`, `extensions/extensions.json`, `pyRevitfile`,
   `.pyrevitargs`;
3. reports whether anything changed.

`extensions/pyRevitTools.extension/` is never touched.

A **scheduled** run stops after step 3 — it pushes nothing. Landing a sync requires
a manual dispatch with `push: true`, and only an actor listed in the
`SYNC_ALLOWED_ACTORS` repository variable may push; anyone else hits the
`Reject unauthorized push` failure.

## Why past runs failed

Both failures were repository settings, not the workflow:

| Run | Failed step | Cause | Resolution |
|---|---|---|---|
| 2026-08-17 | `Create pull request` | GitHub Actions is not permitted to create or approve pull requests | Replaced with the push-based flow, or enable *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests* |
| 2026-10-01 | `Notify pending upstream changes` | Issues are disabled on this repository | The issue is now best-effort and the run falls back to the step summary |

## Overwrite, not merge — the `get_sheet_tblocks` trap

Step 2 is `git checkout upstream/master -- <paths>`: a whole-file overwrite. It does
not merge and it does not warn.

`pyrevitlib/pyrevit/revit/db/query.py` carries one fork-local change
(`get_sheet_tblocks`, recorded in `PYREVITTOOLS_CHANGES.md`) and sits in a synced
path, so **every sync reverts it unless it is re-applied.**

Fork version:

```python
doc = src_sheet.Document
sheet_tblocks = (
    DB.FilteredElementCollector(doc)
    .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
    .WhereElementIsNotElementType()
    .ToElements()
)
return [x for x in sheet_tblocks if x.OwnerViewId == src_sheet.Id]
```

Upstream (identical at 6.5.3 and 7.0):

```python
sheet_tblocks = (
    DB.FilteredElementCollector(src_sheet.Document, src_sheet.Id)
    .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
    .WhereElementIsNotElementType()
    .ToElements()
)
return list(sheet_tblocks)
```

The view-scoped collector forces Revit to regenerate the sheet on every query; the
global collector plus an `OwnerViewId` filter does not.

Opening this change upstream would retire the trap permanently.

## Routine sync (same major version)

```bash
git fetch upstream master
git switch -c core/sync master
git checkout upstream/master -- \
    pyrevitlib \
    site-packages \
    extensions/pyRevitCore.extension \
    extensions/extensions.json \
    pyRevitfile \
    .pyrevitargs
# re-apply the get_sheet_tblocks hunk above, then:
git commit -m "chore: sync pyRevit core from upstream/master"
```

Then work through the validation checklist and deploy.

## Major upgrade (6.5.3 → 7.0.0)

Use a real merge, so fork-local divergence surfaces as a conflict instead of
disappearing:

```bash
git fetch upstream master
git switch -c core/7.0.0 master
git merge --no-commit --no-ff upstream/master

# our extension is entirely ours
git checkout HEAD -- extensions/pyRevitTools.extension

# do NOT keep our whole query.py: upstream grew it substantially, so take
# upstream's file and re-apply only the get_sheet_tblocks hunk above
git checkout upstream/master -- pyrevitlib/pyrevit/revit/db/query.py

git diff --stat master...core/7.0.0 -- \
    pyrevitlib site-packages pyRevitfile .pyrevitargs \
    extensions/pyRevitCore.extension extensions/extensions.json
```

The only fork-authored hunk that diff should show is `get_sheet_tblocks`. Anything
else means a fork change was dropped somewhere and needs recovering.

## 7.0 specifics

Breaking changes, from the
[7.0 release notes](https://github.com/pyrevitlabs/pyRevit/releases/tag/v7.0.0.26278%2B2233):

- **Minimum Revit is now 2021.** The attacher refuses older hosts. The deployment
  currently junctions and attaches 2020–2028, so either drop 2020 before rolling 7.0
  out or hold the fleet on `v6.5.5.26237+2044` (the last 6.5.x release) in the
  meantime.
- `to_net_list` was removed in favour of `to_clr_list` — no usages in this fork.
- Legacy `UIApplication` field fallback removed from the loader.
- Output window moved from the IE WebBrowser to Chromium **WebView2**; the WebView2
  Runtime must be present and allowed on every machine.
- New native payload to account for: `pyrevitlib/pyrevit/agent/`, `automation.py`
  (`pyrevit_automation`), `netrequests.py`, `forms/pyrevit-toast.exe`.
- The agent runtime (MCP server) is opt-in and **defaults to off**. Keep
  `[agent] enabled = false` explicit in the config template.
- `bundle.yaml` is now consulted before inline `__dunder__` metadata; inline
  metadata remains supported (planned through v8).
- Typed C# configuration service, and extension credentials sealed with Windows
  DPAPI. Re-verify `pyrevit config --from` and that `pyRevit_config.ini` stays
  writable.
- IronPython 2 `**kwargs` with a trailing comma is normalised at build time.
- The vendored `markdown` package is deprecated for Python 3.

Unchanged between 6.5.3 and 7.0 (verified against upstream): `pyRevitfile`,
`.pyrevitargs`, the `site-packages` contents, the `[engines]`/`[deployments]`
sections, the IronPython 2.7.12 `DEFAULT` engine, and the loader's
component-postfix map. `.disable` / `.disabled` folders and `.smartbutton` bundles
therefore behave exactly as they did on 6.5.x.

Upstream `pyRevitTools.extension` gained seven bundles (additions only): `Diagnose
Invisibility`, `Automatic Dimensions`, `FilterLegend`, `Wipe AVF`, `Wipe External
Services`, `FamSlide`, plus the `Documentation.pulldown` container. This fork keeps
its own copy of that extension, so they arrive only if cherry-picked deliberately.

## Validation checklist

Run on a canary machine with Revit closed, before touching the fleet:

- [ ] `pyrevit clones info NBRS` reports the expected version.
- [ ] The pyRevit tab loads on every supported Revit version (7.0: 2021+).
- [ ] Disabled bundles are still hidden — the `.disable` folders,
      `.Print Sheets.disabled`, and the `.smartbutton` tools.
- [ ] `get_sheet_tblocks` in the *deployed* clone still uses the `OwnerViewId`
      filter.
- [ ] The output window renders (WebView2).
- [ ] `pyRevit_config.ini` rounds-trips and stays non-read-only.
- [ ] No `FileLoadException` and no `0xc0000409` (SentinelOne, ThreatLocker).
- [ ] NBRSTools and GG-Dev still load and their hooks fire.

## Deployment

Machines run the clone registered as `NBRS` (`C:\ProgramData\pyRevit\NBRS`, branch
`master`, source `https://github.com/nbrs-architecture/pyRevit.git`) — see the
`pyrevit-BatchPatch` repo.

Tools-only update:

```bat
pyrevit-batchpatch.bat -update
```

Core update — required after a core sync, because the loader binaries and engines
change with the core:

```bat
pyrevit-batchpatch.bat -update -full
```

Equivalently, as Administrator with Revit closed and `PYREVIT_CONFIG_SCOPE=allusers`:

```bat
pyrevit clones update --all
pyrevit attach NBRS default --installed --allusers
```

`pyrevit-clone-update.bat` **does** re-seed the machine config from the
`pyRevit_config.ini` sitting next to it, immediately after the clone update:
`pyrevit config --from=<template>`, then `pyrevit clones add NBRS ... --force`.
The previous config is kept as `pyRevit_config.ini.bak`.

Because that is a **full replace**, publish the template to the share *before*
running `-update`. Anything not present in the template is dropped - including
telemetry settings and the `[environment] clones` list. To apply it by hand:

```bat
pyrevit config --from="<share>\pyRevit_config.ini"
pyrevit clones add NBRS "C:\ProgramData\pyRevit\NBRS" --force
```

## Outstanding items

- `get_sheet_tblocks` is still a fork-only change; upstreaming it would remove this
  runbook's central hazard.
- The SentinelOne notes claim `pyrevit-clone-cleanup.bat` runs `takeown` + `icacls`
  first; it does not, so a cleanup under tamper protection can still fail.
- Fork builds are unsigned (upstream stamping only runs on `pyrevitlabs/pyRevit`),
  which is why the loader DLLs need explicit AV/allowlisting exclusions.
