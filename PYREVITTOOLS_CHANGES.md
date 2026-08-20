# PyRevitTools Modifications

Living document tracking every change to `extensions/pyRevitTools.extension/`.
Update this file each time you modify our tools. It is used to reconcile changes
if an upstream core sync ever overlaps with our files.

## Added Tools

| Date | Tool path | Description |
|------|-----------|-------------|
| 2026-08-20 | `extensions/pyRevitTools.extension/pyRevit.tab/Modify.panel/edit2.stack/ReName.pushbutton` | New multipurpose find & replace renamer for family names, views, sheets, filters, and view templates |

## Modified Tools

| Date | Tool path | Change | Reason |
|------|----------|--------|--------|
| 2026-08-20 | `extensions/pyRevitTools.extension/pyRevit.tab/Modify.panel/edit2.stack/ReName.pushbutton/script.py` | Fixed for Revit 2026: replaced `ElementId.IntegerValue` with `pyrevit.compat.get_elementid_value_func()` (version-safe, works 2022+) | `ElementId.IntegerValue` removed in Revit 2026 |
| 2026-08-20 | `extensions/pyRevitTools.extension/pyRevit.tab/Modify.panel/edit2.stack/ReValue.pushbutton` | Disabled ReValue: renamed `ReValue.pushbutton` to `ReValue.disable` | Tool not needed on this deployment; re-enable by renaming back |
| 2026-08-17 | `extensions/pyRevitTools.extension/pyRevit.tab/Drawing Set.panel/Print Sheets.pushbutton` | Renamed bundle folder to `.Print Sheets.disabled` (non-component postfix + dot-prefix) so both the Python parser and the new C# loader skip it — button hidden from the Drawing Set panel, all assets preserved | Tool not needed on this deployment; re-enable by renaming back |
| 2026-08-17 | `extensions/pyRevitTools.extension/pyRevit.tab/Project.panel/Wipe.pulldown/` | Disabled in-use components wipe: renamed the seven Wipe `.pushbutton` folders to `.disable` | Tools not needed on this deployment; re-enable by renaming back |
| 2026-08-17 | `extensions/pyRevitTools.extension/pyRevit.tab/Selection.panel/mema.stack` and `memo.stack` | Disabled memo and mema stacks: renamed to `mema.disable` / `memo.disable` | Stacks not needed on this deployment; re-enable by renaming back |

## Removed Tools

| Date | Tool path | Reason |
|------|----------|--------|
| _None yet_ | | |
