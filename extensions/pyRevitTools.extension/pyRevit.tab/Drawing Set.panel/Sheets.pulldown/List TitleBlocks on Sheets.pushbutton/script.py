"""Select title blocks on selected sheets for batch editing.

Shift+Click:
Skip the sheet selector popup.
Select titleblocks on currently selected sheets in project browser.

"""
# pylint: disable=import-error,invalid-name,broad-except,superfluous-parens
from pyrevit import revit, EXEC_PARAMS
from pyrevit import forms
from pyrevit import script

output = script.get_output()
logger = script.get_logger()

SCALE_PARAM_NAME = "Scale"


def get_source_sheets():
    sheet_elements = forms.select_sheets(
        button_name="List TitleBlocks",
        use_selection=True,
        include_placeholder=False,
    )
    if not sheet_elements:
        script.exit()
    return sheet_elements


def get_sheet_scale(sheet):
    """Return the sheet 'Scale' parameter as displayed text."""
    for param in sheet.GetOrderedParameters():
        if param.Definition and param.Definition.Name == SCALE_PARAM_NAME:
            value = param.AsString()
            if not value:
                value = param.AsValueString()
            return value or ""
    return ""


def get_sheet_views(sheet):
    """Return linked, comma separated names of the views placed on sheet."""
    views = []
    for view_id in sheet.GetAllPlacedViews():
        view = revit.doc.GetElement(view_id)
        if view is not None:
            views.append((view.Name, output.linkify(view.Id, title=view.Name)))
    views.sort(key=lambda x: x[0])
    return ", ".join([x[1] for x in views])


def print_titleblocks(sheets):
    all_tblocks = []
    sheet_rows = []
    for sheet in sheets:
        tblocks = revit.query.get_sheet_tblocks(sheet)
        if not tblocks:
            continue
        all_tblocks.extend([x.Id for x in tblocks])
        sheet_rows.append((sheet, tblocks))

    sheet_rows.sort(key=lambda x: x[0].SheetNumber)

    table_data = []
    for sheet, tblocks in sheet_rows:
        table_data.append(
            [
                output.linkify(
                    sheet.Id,
                    title="{0} - {1}".format(sheet.SheetNumber, sheet.Name),
                ),
                ", ".join(
                    [output.linkify(x.Id, title=x.Name) for x in tblocks]
                ),
                get_sheet_views(sheet),
                get_sheet_scale(sheet),
            ]
        )

    if table_data:
        output.print_table(
            table_data=table_data,
            title="TitleBlocks on Sheets",
            columns=["SHEET", "TITLEBLOCK", "VIEWS", "SCALE"],
        )
    else:
        forms.alert("No titleblocks found on the selected sheets.")

    if all_tblocks:
        print(
            "{}".format(
                output.linkify(all_tblocks, title="Select All TitleBlocks")
            )
        )


# orchestrate
if EXEC_PARAMS.config_mode:
    selection = revit.get_selection()
    sheets = get_source_sheets()
    all_tblocks = []
    for sheet in sheets:
        tblocks = revit.query.get_sheet_tblocks(sheet)
        all_tblocks.extend([x.Id for x in tblocks])
    selection.set_to(all_tblocks)
else:
    print_titleblocks(get_source_sheets())
