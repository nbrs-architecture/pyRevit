"""ReName - multipurpose find & replace renamer.

Element-agnostic: pick a target (Family Names, Views, Sheets, Filters, or
View Templates), enter a string to find, select the matching items to
rename, then enter the replacement string.

All UI is built from pyRevit forms (no third-party windows).
"""
#pylint: disable=import-error,invalid-name,broad-except
from pyrevit import revit, DB
from pyrevit import forms
from pyrevit.compat import get_elementid_value_func


# ---------------------------------------------------------------------------
# target collectors
# ---------------------------------------------------------------------------
def _collect_families(doc):
    return DB.FilteredElementCollector(doc).OfClass(DB.Family).ToElements()


def _collect_views(doc):
    return [v for v in revit.query.get_all_views(doc=doc) if not v.IsTemplate]


def _collect_sheets(doc):
    return (DB.FilteredElementCollector(doc)
            .OfClass(DB.ViewSheet)
            .WhereElementIsNotElementType()
            .ToElements())


def _collect_filters(doc):
    return (DB.FilteredElementCollector(doc)
            .OfClass(DB.ParameterFilterElement)
            .ToElements())


def _collect_viewtemplates(doc):
    return revit.query.get_all_view_templates(doc=doc)


COLLECTORS = {
    'Family Names': _collect_families,
    'Views': _collect_views,
    'Sheets': _collect_sheets,
    'Filters': _collect_filters,
    'View Templates': _collect_viewtemplates,
}


class ReNameItem(forms.TemplateListItem):
    """Checkbox item showing the element's name in the selection list."""

    def __init__(self, element, checked=True):
        super(ReNameItem, self).__init__(element, checked=checked)

    @property
    def name(self):
        return revit.query.get_name(self.item)


def _set_name(element, new_name):
    """Rename an element, handling families via their name parameter."""
    if isinstance(element, DB.Family):
        fam_name_param = element.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if fam_name_param and not fam_name_param.IsReadOnly:
            fam_name_param.Set(new_name)
            return
    revit.update.set_name(element, new_name)


def _apply_renames(doc, rename_pairs):
    """Rename elements in one transaction.

    Args:
        rename_pairs (list): list of (element, new_name) tuples

    Returns:
        (list, list, list): renamed, conflicts, failed
    """
    renamed = []
    conflicts = []
    failed = []
    seen_names = {}
    get_elementid_value = get_elementid_value_func()

    with revit.Transaction('ReName', doc=doc):
        for element, new_name in rename_pairs:
            old_name = revit.query.get_name(element)
            new_key = new_name.lower()
            # avoid name collisions within the same batch
            if (new_key in seen_names
                    and seen_names[new_key] != get_elementid_value(element.Id)):
                conflicts.append((element, old_name, new_name))
                continue
            seen_names[new_key] = get_elementid_value(element.Id)
            try:
                _set_name(element, new_name)
                renamed.append((element, old_name, new_name))
            except Exception as exc:
                failed.append((element, old_name, new_name, str(exc)))

    return renamed, conflicts, failed


def _print_report(renamed, conflicts, failed):
    print('ReName - results')
    print('  Renamed: {}'.format(len(renamed)))
    print('  Conflicts (duplicate target name): {}'.format(len(conflicts)))
    print('  Failed: {}'.format(len(failed)))

    if renamed:
        print('\nRenamed:')
        for element, old_name, new_name in renamed:
            print('  {}  -->  {}'.format(old_name, new_name))
    if conflicts:
        print('\nConflicts (target name already used in this batch):')
        for element, old_name, new_name in conflicts:
            print('  {}  -->  {}'.format(old_name, new_name))
    if failed:
        print('\nFailed:')
        for element, old_name, new_name, err in failed:
            print('  {}  -->  {}  ({})'.format(old_name, new_name, err))


def main():
    doc = revit.doc

    # 1) pick what to rename
    target = forms.CommandSwitchWindow.show(
        sorted(COLLECTORS.keys()),
        message='What do you want to rename?')
    if not target:
        return

    # 2) find string
    find_str = forms.ask_for_string(prompt='Find:', title='ReName - Find')
    if not find_str:
        return

    # 3) gather matching candidates and let the user select which to rename
    matching = []
    for element in COLLECTORS[target](doc):
        old_name = revit.query.get_name(element)
        if old_name and find_str in old_name:
            matching.append(ReNameItem(element))

    matching.sort(key=lambda x: x.name)

    if not matching:
        forms.alert(
            'Could not find "{}" in any {} names.'.format(
                find_str, target.lower()),
            title='ReName',
            exitscript=True)

    selected = forms.SelectFromList.show(
        matching,
        title='ReName - Select {}'.format(target),
        button_name='Next',
        multiselect=True,
    )

    if not selected:
        forms.alert('No items selected. Nothing renamed.',
                    title='ReName',
                    exitscript=True)

    # 4) replacement string (entered after the selection)
    replace_str = forms.ask_for_string(
        default='', prompt='Replace with:', title='ReName - Replace with')
    if replace_str is None:
        return

    # 5) build rename pairs and apply
    rename_pairs = []
    for element in selected:
        old_name = revit.query.get_name(element)
        new_name = old_name.replace(find_str, replace_str)
        if new_name and new_name != old_name:
            rename_pairs.append((element, new_name))

    if not rename_pairs:
        forms.alert('No valid new names. Nothing renamed.',
                    title='ReName',
                    exitscript=True)

    renamed, conflicts, failed = _apply_renames(doc, rename_pairs)
    _print_report(renamed, conflicts, failed)
    forms.alert(
        'Done.\nRenamed: {}\nConflicts: {}\nFailed: {}'.format(
            len(renamed), len(conflicts), len(failed)),
        title='ReName')


if __name__ == '__main__':
    main()
