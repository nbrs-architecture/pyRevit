# -*- coding: utf-8 -*-
"""CAD files must be LINKED, never IMPORTED.

pyRevit hook: ``command-before-exec[ID_FILE_IMPORT]``

``ID_FILE_IMPORT`` is the ribbon command "Insert > Import > Import CAD".
The dialog accepts DWG, DXF, DGN, and SAT — all are blocked by this hook.
``ID_FILE_CADFORMAT_LINK`` ("Insert > Link > Link CAD") is a separate command
and is left untouched. Both IDs are identical in Revit 2022, 2024, and 2026.
3DM (Rhino) files have their own command ID and are not affected.

Why not a ``file-importing`` hook: Revit raises ``Application.FileImporting``
for linked CAD as well as for imported CAD, and ``FileImportingEventArgs``
exposes only ``Format`` and ``Path`` (checked against ``RevitAPI.xml`` for
2022/2024/2026), so a hook on that event cannot tell the two apart and would
cancel Link CAD too. ``BeforeExecutedEventArgs`` is documented as cancellable,
so the command is stopped before it runs: nothing is created, nothing has to be
deleted afterwards and no cancel-and-redo pair lands in the undo stack.

Family documents are exempt: content authors legitimately import CAD, so the
hook only blocks imports in project documents.

Imports that never reach this ribbon command - drag-and-drop, or another add-in
calling ``Document.Import()`` - are not blocked by this hook.

Intentionally no try/except: if this hook ever breaks, it should say so.
"""
#pylint: disable=import-error,invalid-name

from pyrevit import EXEC_PARAMS, forms


TITLE = 'IMPORT CAD'
SUGGESTION = 'Use LINK CAD please.'


def main():
    """Cancel Import CAD and point the user at Link CAD instead."""
    # event_sender is the UIApplication; ActiveDocument on BeforeExecutedEventArgs
    # has no backing property in the Revit API and returns None unreliably.
    uidoc = EXEC_PARAMS.event_sender.ActiveUIDocument
    doc = uidoc.Document if uidoc else None

    # Family documents may import CAD while authoring content; leave the event
    # alone and exit without an alert. This must happen before Cancel is set:
    # Revit cannot un-cancel an event and raises InvalidOperationException.
    if doc is not None and doc.IsFamilyDocument:
        return

    # Cancel is a bool property on BeforeExecutedEventArgs - assign it, never call it.
    EXEC_PARAMS.event_args.Cancel = True

    # Only alert when a model document is active; if doc is None the command
    # is already cancelled silently (Import CAD is disabled with no doc open).
    if doc is not None:
        forms.alert(
            SUGGESTION,
            title=TITLE,
            options=['Close'],
            exitscript=False
        )


if __name__ == '__main__':
    main()
