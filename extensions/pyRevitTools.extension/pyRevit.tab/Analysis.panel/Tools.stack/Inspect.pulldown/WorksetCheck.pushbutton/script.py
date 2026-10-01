# -*- coding: utf-8 -*-
"""List elements grouped by workset, broken down by category.

Collects every user workset in the model and, for each one, counts the
elements assigned to it grouped by their category.

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


def get_workset_elements(doc, workset):
    """Return the non-type elements assigned to a single workset."""
    return list(
        DB.FilteredElementCollector(doc)
        .WherePasses(DB.ElementWorksetFilter(workset.Id))
        .WhereElementIsNotElementType()
        .ToElements()
    )


def get_category_counts(elements):
    """Group elements by category name and count them.

    Elements without a category are ignored, and so are banned system
    categories.
    """
    category_counts = defaultdict(int)

    for element in elements:
        try:
            category = element.Category
        except Exception:
            # some elements (e.g. Project Information) have no category
            continue

        if category is None:
            continue

        cat_id_value = get_elementid_value(category.Id)
        # only count system categories (negative ids) that aren't banned
        if cat_id_value < 0 and cat_id_value not in CATEGORY_BAN_LIST:
            category_counts[category.Name] += 1

    return category_counts


def main():
    doc = revit.doc
    if not forms.check_workshared(doc):
        script.exit()

    worksets = list(
        DB.FilteredWorksetCollector(doc)
        .OfKind(DB.WorksetKind.UserWorkset)
        .ToWorksets()
    )

    if not worksets:
        forms.alert('No Worksets in model.', exitscript=True)

    for workset in worksets:
        elements = get_workset_elements(doc, workset)

        if not elements:
            output.print_md('### WORKSET: {} - EMPTY'.format(workset.Name))
            continue

        category_counts = get_category_counts(elements)
        total_count = sum(category_counts.values())

        output.print_md('### WORKSET: {}'.format(workset.Name))
        print('Breakdown by Category:')

        # most populated categories first, then alphabetically
        for cat_name, count in sorted(category_counts.items(),
                                      key=lambda item: (-item[1], item[0])):
            print('.......{0} : {1}'.format(cat_name, count))

        print('.......TOTAL : {0} elements'.format(total_count))


if __name__ == '__main__':
    main()
