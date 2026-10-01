# -*- coding: utf-8 -*-
"""List all elements of the selected workset(s).

Asks the user to pick one or more worksets and then lists every element in
them, grouped by category.

Works on Revit 2022+.
"""

from collections import defaultdict

from pyrevit import forms
from pyrevit import revit, DB
from pyrevit import script
from pyrevit.compat import get_elementid_value_func


output = script.get_output()
get_elementid_value = get_elementid_value_func()


# BuiltInCategory ids are negative integers. System categories that only
# inflate the counts with non-meaningful items (dimensions, sketch geometry,
# stairs sub-elements, curtain wall infrastructure, ...) are skipped.
CATEGORY_BAN_LIST = {
    -2000260,   # Dimensions
    -2000261,   # Automatic Sketch Dimensions
    -2000954,   # Railing Path Extension Lines
    -2000045,   # <Sketch>
    -2000067,   # <Stair/Ramp Sketch: Boundary>
    -2000262,   # Constraints
    -2000920,   # Landings
    -2000919,   # Stair runs
    -2000123,   # Supports
    -2000173,   # Curtain Wall Grids
    -2000171,   # Curtain Wall Mullions
    -2000170,   # Curtain Panels
    -2000530,   # Reference Planes
    -2000127,   # Balusters
    -2000947,   # Handrail
    -2000946,   # Top Rail
}


class WorksetOption(forms.TemplateListItem):
    """Workset wrapper so the picker lists the workset name."""

    @property
    def name(self):
        return self.item.Name


def get_user_worksets(doc):
    """Return all user worksets in the model."""
    return list(
        DB.FilteredWorksetCollector(doc)
        .OfKind(DB.WorksetKind.UserWorkset)
        .ToWorksets()
    )


def select_worksets(doc):
    """Prompt the user for one or more worksets."""
    all_worksets = get_user_worksets(doc)
    if not all_worksets:
        forms.alert('No Worksets in model.', exitscript=True)

    return forms.SelectFromList.show(
        sorted([WorksetOption(workset) for workset in all_worksets],
               key=lambda option: option.name),
        title='Select Worksets',
        button_name='Select Worksets',
        width=500,
        multiselect=True,
        checked_only=True
    )


def get_workset_elements(doc, workset):
    """Return the non-type elements assigned to a single workset."""
    return list(
        DB.FilteredElementCollector(doc)
        .WherePasses(DB.ElementWorksetFilter(workset.Id))
        .WhereElementIsNotElementType()
        .ToElements()
    )


def group_by_category(elements):
    """Group elements by category name.

    Elements without a category are ignored, and so are banned system
    categories.
    """
    categorized = defaultdict(list)

    for element in elements:
        try:
            category = element.Category
        except Exception:
            # some elements (e.g. Project Information) have no category
            continue

        if category is None:
            continue

        cat_id_value = get_elementid_value(category.Id)
        # only keep system categories (negative ids) that aren't banned
        if cat_id_value < 0 and cat_id_value not in CATEGORY_BAN_LIST:
            categorized[category.Name].append(element)

    return categorized


def list_workset(doc, workset):
    """Print every element of a workset, grouped by category."""
    elements = get_workset_elements(doc, workset)

    if not elements:
        output.print_md('#### WORKSET: {} - EMPTY'.format(workset.Name))
        return

    categorized = group_by_category(elements)
    total_count = sum(len(items) for items in categorized.values())

    print('\n' + '╞═════════■ {}:'.format(workset.Name))

    # most populated categories first, then alphabetically
    for cat_name in sorted(categorized,
                           key=lambda name: (-len(categorized[name]), name)):
        category_elements = categorized[cat_name]
        print('├──────────□ {}: {}'.format(cat_name, len(category_elements)))

        for element in category_elements:
            print('├ id: {}'.format(output.linkify(element.Id)))

    print('├────────── {} Categories found in {}:'
          .format(len(categorized), workset.Name))

    for cat_name in sorted(categorized):
        print('│ {}: {}'.format(cat_name, len(categorized[cat_name])))

    print('└────────── {}: {} Elements found.'
          .format(workset.Name, total_count))


def main():
    doc = revit.doc
    if not forms.check_workshared(doc):
        script.exit()

    worksets = select_worksets(doc)
    if not worksets:
        script.exit()

    output.print_md('####LIST ALL ELEMENTS OF SELECTED WORKSET(S):')

    for workset in worksets:
        list_workset(doc, workset)


if __name__ == '__main__':
    main()
