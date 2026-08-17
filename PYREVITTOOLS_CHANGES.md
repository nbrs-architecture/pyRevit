# PyRevitTools Modifications

Living document tracking every change to `extensions/pyRevitTools.extension/`.
Update this file each time you modify our tools. It is used to reconcile changes
if an upstream core sync ever overlaps with our files.

## Added Tools

| Date | Tool path | Description |
|------|-----------|-------------|
| _None yet_ | | |

## Modified Tools

| Date | Tool path | Change | Reason |
|------|----------|--------|--------|
| 2026-08-17 | `extensions/pyRevitTools.extension/pyRevit.tab/Drawing Set.panel/Print Sheets.pushbutton` | Renamed bundle folder to `.Print Sheets.disabled` (non-component postfix + dot-prefix) so both the Python parser and the new C# loader skip it — button hidden from the Drawing Set panel, all assets preserved | Tool not needed on this deployment; re-enable by renaming back |
| 2026-08-17 | `extensions/pyRevitTools.extension/pyRevit.tab/Project.panel/Wipe.pulldown/` | Disabled in-use components wipe: renamed the seven Wipe `.pushbutton` folders to `.disable` | Tools not needed on this deployment; re-enable by renaming back |
| 2026-08-17 | `extensions/pyRevitTools.extension/pyRevit.tab/Selection.panel/mema.stack` and `memo.stack` | Disabled memo and mema stacks: renamed to `mema.disable` / `memo.disable` | Stacks not needed on this deployment; re-enable by renaming back |

## Removed Tools

| Date | Tool path | Reason |
|------|----------|--------|
| _None yet_ | | |
