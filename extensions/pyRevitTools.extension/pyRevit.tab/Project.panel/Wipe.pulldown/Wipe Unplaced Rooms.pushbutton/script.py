# -*- coding: utf-8 -*-
"""Wipe unplaced rooms.

Collects every room in the project, works out which ones have never been
placed (no location), and lists the unplaced ones so the user can
multi-select which to wipe.

Unplaced rooms are created e.g. by adding rows to a room schedule; they do
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


def room_label(room):
    """Return a 'Number - Name' label for the room list."""
    number = _param_string(room, DB.BuiltInParameter.ROOM_NUMBER)
    name = _param_string(room, DB.BuiltInParameter.ROOM_NAME)
    if number and name:
        return '{} - {}'.format(number, name)
    return number or name or 'Unnamed Room'


class RoomToWipe(forms.TemplateListItem):
    @property
    def name(self):
        return room_label(self.item)


def main():
    doc = revit.doc
    if doc.IsFamilyDocument:
        forms.alert('This tool works on project documents only.',
                    exitscript=True)

    rooms = DB.FilteredElementCollector(doc)\
              .OfCategory(DB.BuiltInCategory.OST_Rooms)\
              .WhereElementIsNotElementType()\
              .ToElements()

    if not rooms:
        forms.alert('No rooms found in the model. Nothing to wipe.',
                    exitscript=True)

    # an unplaced room has no location (it only shows up in room schedules)
    unplaced_rooms = [room for room in rooms if room.Location is None]

    if not unplaced_rooms:
        forms.alert('All rooms are placed. Nothing to wipe.',
                    exitscript=True)

    logger.debug('{} of {} rooms are unplaced'
                 .format(len(unplaced_rooms), len(rooms)))

    # ask user which unplaced rooms to wipe
    return_options = \
        forms.SelectFromList.show(
            [RoomToWipe(room) for room in unplaced_rooms],
            title='Select Unplaced Rooms to Wipe ({})'
                  .format(len(unplaced_rooms)),
            width=500,
            button_name='Wipe Rooms',
            multiselect=True
            )

    if not return_options:
        script.exit()

    with revit.Transaction('Wipe Unplaced Rooms'):
        for room in return_options:
            logger.debug('Wiping room: {0}\t{1}'
                         .format(room.Id, room_label(room)))
            try:
                doc.Delete(room.Id)
            except Exception as del_err:
                logger.error('Error wiping room: {} | {}'
                             .format(room_label(room), del_err))


if __name__ == '__main__':
    main()
