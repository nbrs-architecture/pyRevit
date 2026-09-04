# -*- coding: utf-8 -*-
"""Wipe unused scope boxes.

Collects every scope box in the project, works out which ones are still in
use, and lists the unused ones so the user can multi-select which to wipe.

Usage detection (classic purge routine, adapted from pyChilizer):
  - views that can carry a scope box crop  -> VIEWER_VOLUME_OF_INTEREST_CROP
  - datum elements (levels, grids) scoped  -> DATUM_VOLUME_OF_INTEREST

Works on Revit 2022+ (ElementId access via pyrevit.compat).
"""

from pyrevit import forms
from pyrevit import revit, DB
from pyrevit import script
from pyrevit.compat import get_elementid_value_func


logger = script.get_logger()


class ScopeBoxToPurge(forms.TemplateListItem):
    @property
    def name(self):
        return self.item.Name


# view families that can have a scope box applied to their crop region
_SB_VIEW_TYPES = (
    DB.ViewType.FloorPlan,
    DB.ViewType.CeilingPlan,
    DB.ViewType.EngineeringPlan,
    DB.ViewType.AreaPlan,
    DB.ViewType.Section,
    DB.ViewType.Elevation,
    DB.ViewType.Detail,
    DB.ViewType.ThreeD,
)

# datum element categories that can be scoped to a scope box
_SB_DATUM_CATEGORIES = (
    DB.BuiltInCategory.OST_Levels,
    DB.BuiltInCategory.OST_Grids,
)

get_elementid_value = get_elementid_value_func()


def _as_scope_value(parameter):
    """Return the integer ElementId value if the parameter references a scope
    box, otherwise 0. A missing parameter / failed read = 'not scoped'.
    """
    if parameter is None:
        return 0
    try:
        sb_id = parameter.AsElementId()
    except Exception:
        return 0
    if sb_id == DB.ElementId.InvalidElementId:
        return 0
    return get_elementid_value(sb_id)


def _collect_used_scope_ids():
    """Return the set of integer ElementId values of scope boxes in use."""
    used = set()

    # views whose crop region is locked to a scope box
    views = DB.FilteredElementCollector(revit.doc)\
              .OfClass(DB.View)\
              .WhereElementIsNotElementType()\
              .ToElements()
    for view in views:
        if view.ViewType not in _SB_VIEW_TYPES:
            continue
        sb_val = _as_scope_value(
            view.get_Parameter(
                DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP))
        if sb_val:
            used.add(sb_val)

    # datum elements (levels, grids) scoped to a scope box
    for cat in _SB_DATUM_CATEGORIES:
        datums = DB.FilteredElementCollector(revit.doc)\
                   .OfCategory(cat)\
                   .WhereElementIsNotElementType()\
                   .ToElements()
        for datum in datums:
            sb_val = _as_scope_value(
                datum.get_Parameter(
                    DB.BuiltInParameter.DATUM_VOLUME_OF_INTEREST))
            if sb_val:
                used.add(sb_val)

    return used


def main():
    doc = revit.doc
    if doc.IsFamilyDocument:
        forms.alert('This tool works on project documents only.',
                    exitscript=True)

    scopeboxes = DB.FilteredElementCollector(doc)\
                   .OfCategory(DB.BuiltInCategory.OST_VolumeOfInterest)\
                   .WhereElementIsNotElementType()\
                   .ToElements()

    if not scopeboxes:
        forms.alert('No scope boxes found in the model. Nothing to wipe.',
                    exitscript=True)

    all_scope_ids = set(get_elementid_value(sb.Id) for sb in scopeboxes)
    unused_scope_ids = all_scope_ids - _collect_used_scope_ids()

    if not unused_scope_ids:
        forms.alert('All scope boxes are in use. Nothing to wipe.',
                    exitscript=True)

    logger.debug('{} of {} scope boxes are unused'
                 .format(len(unused_scope_ids), len(all_scope_ids)))

    # ask user which unused scope boxes to wipe
    return_options = \
        forms.SelectFromList.show(
            [ScopeBoxToPurge(doc.GetElement(DB.ElementId(x)))
             for x in unused_scope_ids],
            title='Select Unused Scope Boxes to Wipe ({})'
                  .format(len(unused_scope_ids)),
            width=500,
            button_name='Wipe Scope Boxes',
            multiselect=True
            )

    if not return_options:
        script.exit()

    with revit.Transaction('Wipe Unused Scope Boxes'):
        for sb in return_options:
            logger.debug('Wiping scope box: {0}\t{1}'
                         .format(sb.Id, sb.Name))
            try:
                doc.Delete(sb.Id)
            except Exception as del_err:
                logger.error('Error wiping scope box: {} | {}'
                             .format(sb.Name, del_err))


if __name__ == '__main__':
    main()
