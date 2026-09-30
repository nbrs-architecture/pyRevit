# -*- coding: utf-8 -*-
"""Wipe unplaced areas.

Collects every area in the project, works out which ones have never been
placed (no location), and lists the unplaced ones so the user can
multi-select which to wipe.

Unplaced areas are created e.g. by adding rows to an area schedule; they do
not exist in any view and can be safely removed.

Works on Revit 2022+.
"""

from pyrevit import forms
from pyrevit import revit, DB
from pyrevit import script


logger = script.get_logger()


def _safe(text):
    """ASCII-safe string (protects IronPython 2.7 output from unicode errors)."""
    if text is None:
        return ''
    return text.encode('ascii', 'replace').decode('ascii')


def _param_string(element, bip):
    """Read a string parameter, falling back to its formatted value."""
    param = element.get_Parameter(bip)
    if param is None:
        return ''
    value = param.AsString()
    if value is None:
        value = param.AsValueString()
    return _safe(value)


def area_label(area):
    """Return a 'Number - Name' label for the area list."""
    number = _param_string(area, DB.BuiltInParameter.ROOM_NUMBER)
    name = _param_string(area, DB.BuiltInParameter.ROOM_NAME)
    if number and name:
        return '{} - {}'.format(number, name)
    return number or name or 'Unnamed Area'


class AreaToWipe(forms.TemplateListItem):
    @property
    def name(self):
        return area_label(self.item)


def main():
    doc = revit.doc
    if doc.IsFamilyDocument:
        forms.alert('This tool works on project documents only.',
                    exitscript=True)

    areas = DB.FilteredElementCollector(doc)\
              .OfCategory(DB.BuiltInCategory.OST_Areas)\
              .WhereElementIsNotElementType()\
              .ToElements()

    if not areas:
        forms.alert('No areas found in the model. Nothing to wipe.',
                    exitscript=True)

    # an unplaced area has no location (it only shows up in area schedules)
    unplaced_areas = [area for area in areas if area.Location is None]

    if not unplaced_areas:
        forms.alert('All areas are placed. Nothing to wipe.',
                    exitscript=True)

    logger.debug('{} of {} areas are unplaced'
                 .format(len(unplaced_areas), len(areas)))

    # ask user which unplaced areas to wipe
    return_options = \
        forms.SelectFromList.show(
            [AreaToWipe(area) for area in unplaced_areas],
            title='Select Unplaced Areas to Wipe ({})'
                  .format(len(unplaced_areas)),
            width=500,
            button_name='Wipe Areas',
            multiselect=True
            )

    if not return_options:
        script.exit()

    with revit.Transaction('Wipe Unplaced Areas'):
        for area in return_options:
            logger.debug('Wiping area: {0}\t{1}'
                         .format(area.Id, area_label(area)))
            try:
                doc.Delete(area.Id)
            except Exception as del_err:
                logger.error('Error wiping area: {} | {}'
                             .format(area_label(area), del_err))


if __name__ == '__main__':
    main()
