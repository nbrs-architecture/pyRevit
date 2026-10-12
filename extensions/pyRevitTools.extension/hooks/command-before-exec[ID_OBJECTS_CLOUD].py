# -*- coding: utf-8 -*-
"""Revision clouds are only allowed on drawing sheets.

pyRevit hook: ``command-before-exec[ID_OBJECTS_CLOUD]``

``ID_OBJECTS_CLOUD`` is the ribbon command "Create a revision cloud", as
recorded in a Revit journal:

    Jrn.Command "Ribbon"  , "Create a revision cloud , ID_OBJECTS_CLOUD"

``BeforeExecutedEventArgs`` is cancellable, so the tool is stopped before it
starts: nothing is created, nothing has to be deleted afterwards and no
cancel-and-redo pair lands in the undo stack. That is why this rule lives in a
command hook and not in ``doc-changed`` - Application.DocumentChanged is
documented as a read-only event with no cancel, so it can only report a cloud
that already exists.

Intentionally no try/except: if this hook ever breaks, it should say so.
"""
#pylint: disable=import-error,invalid-name

from pyrevit import DB, EXEC_PARAMS, forms


TITLE = 'REVISION CLOUD IN VIEW'
MESSAGE = ('Revision Clouds must be placed on SHEETS.')


def is_sheet(view):
    """Only a drawing sheet may host a revision cloud."""
    return view is not None and view.ViewType == DB.ViewType.DrawingSheet


def main():
    """Cancel the revision cloud tool unless the active view is a sheet."""
    args = EXEC_PARAMS.event_args

    doc = args.ActiveDocument
    if doc is None:
        return

    if is_sheet(doc.ActiveView):
        return

    # Cancel is a bool property on RevitEventArgs - assign it, never call it
    args.Cancel = True

    forms.alert(MESSAGE, title=TITLE, exitscript=False)


if __name__ == '__main__':
    main()
