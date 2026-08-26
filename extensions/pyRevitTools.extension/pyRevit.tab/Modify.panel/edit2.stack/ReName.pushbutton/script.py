# -*- coding: utf-8 -*-
"""ReName - single-form find & replace renamer (HTML UI).

Built on the shared uiUtils.html dialog library: the UI is a plain HTML file
(rename.html) and the rename logic is wired to it via @action handlers.

Pick a target category, then a single HTML form shows FIND / REPLACE inputs
next to a live-filtered list of matching items. As you type in FIND the list
filters down instantly (client-side JS) with matching text highlighted.
"Match Exact" toggles case-sensitive matching; Rename applies in one undo step
and highlights the changes green inline - no extra dialogs or alerts.
"""
#pylint: disable=import-error,invalid-name,broad-except
import re

from pyrevit import revit, DB
from pyrevit import forms
from pyrevit.compat import get_elementid_value_func

from uiUtils.html import HtmlDialog, action


# ---------------------------------------------------------------------------
# target collectors
# ---------------------------------------------------------------------------
def _family_name(element):
    """Return the family name of a Family or FamilySymbol (incl. system families).

    Loadable families are DB.Family elements. System families (walls, floors,
    ceilings, stairs, ...) are not Family elements in the database, so each is
    represented by one of its FamilySymbol types. ElementType.FamilyName (and
    the ALL_MODEL_FAMILY_NAME parameter) return the family name for both kinds.
    """
    if isinstance(element, DB.FamilySymbol):
        fam_name = element.FamilyName
        if fam_name:
            return fam_name
        fam_param = element.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if fam_param and fam_param.HasValue:
            return fam_param.AsString()
    return revit.query.get_name(element)


def _element_category(element):
    """Return the Category of a family element.

    DB.Family exposes it via FamilyCategory - Element.Category can be None for
    Family elements in some engines, which left loadable-family categories blank.
    """
    if isinstance(element, DB.Family):
        return element.FamilyCategory
    return element.Category


def _family_category(element):
    """Return the category display name of a family (e.g. 'Walls')."""
    cat = _element_category(element)
    return cat.Name if cat else ''


# system families are not Family elements in the database, so they are
# collected separately per category
_SYSTEM_FAMILY_CATEGORIES = [
    DB.BuiltInCategory.OST_Walls,
    DB.BuiltInCategory.OST_Floors,
    DB.BuiltInCategory.OST_Ceilings,
    DB.BuiltInCategory.OST_Roofs,
    DB.BuiltInCategory.OST_Stairs,
    DB.BuiltInCategory.OST_Ramps,
    DB.BuiltInCategory.OST_Railings,
]


def _collect_families(doc):
    """Collect loadable families + system families (walls, floors, ceilings, ...).

    Loadable families are DB.Family elements. System families are not Family
    elements in the database, so each system family type is collected separately
    via its BuiltInCategory and deduped by (category, family name).
    """
    get_elementid_value = get_elementid_value_func()
    fam_map = {}

    def _cat_id(element):
        cat = _element_category(element)
        return get_elementid_value(cat.Id) if cat else 0

    # loadable (component) families - represented by their Family element
    # (ALL_MODEL_FAMILY_NAME can be read-only on the Family element, so do not
    # gate collection on it - renaming handles that separately)
    for fam in (DB.FilteredElementCollector(doc)
                .OfClass(DB.Family).ToElements()):
        try:
            fam_map[(_cat_id(fam), _family_name(fam))] = fam
        except Exception:
            continue

    # system families collected separately per category
    for bic in _SYSTEM_FAMILY_CATEGORIES:
        try:
            syms = (DB.FilteredElementCollector(doc)
                    .OfCategory(bic)
                    .WhereElementIsElementType()
                    .ToElements())
        except Exception:
            continue
        for sym in syms:
            try:
                key = (_cat_id(sym), _family_name(sym))
            except Exception:
                continue
            fam_map.setdefault(key, sym)

    return fam_map.values()


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


# ---------------------------------------------------------------------------
# rename logic
# ---------------------------------------------------------------------------
_doc = None
_target = None
_elem_by_id = {}
_renamed = []
_conflicts = []
_failed = []


def _display_name(element):
    """Name shown/edited for the current target.

    Family Names shows just the family name (the category is a separate column
    in the UI and is ignored by find/replace); other targets use the plain
    element name.
    """
    if _target == 'Family Names':
        return _family_name(element)
    return revit.query.get_name(element)


def _set_name(element, new_name):
    """Rename an element.

    Loadable families (DB.Family) are renamed via ALL_MODEL_FAMILY_NAME (or the
    Family.Name setter as fallback). System families (represented by one of
    their FamilySymbol types) are renamed via ALL_MODEL_FAMILY_NAME, which
    renames the whole system family at once.
    """
    if isinstance(element, DB.FamilySymbol):
        fam_name_param = element.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if fam_name_param and not fam_name_param.IsReadOnly:
            fam_name_param.Set(new_name)
            return
        raise Exception('Family name parameter is read-only.')
    if isinstance(element, DB.Family):
        fam_name_param = element.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if fam_name_param and not fam_name_param.IsReadOnly:
            fam_name_param.Set(new_name)
            return
        # ALL_MODEL_FAMILY_NAME is read-only here -> use the Family.Name setter
        element.Name = new_name
        return
    revit.update.set_name(element, new_name)


def _apply_renames(doc, rename_pairs):
    """Rename elements in one transaction.

    Returns (renamed, conflicts, failed) lists.
    """
    renamed = []
    conflicts = []
    failed = []
    seen_names = {}
    get_elementid_value = get_elementid_value_func()

    with revit.Transaction('ReName', doc=doc):
        for element, new_name in rename_pairs:
            old_name = _display_name(element)
            new_key = new_name.lower()
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


@action('rename')
def _do_rename(dlg, payload):
    """Run the rename from the open form; reply with per-id changes."""
    global _renamed, _conflicts, _failed
    find_str = payload.get('find', '')
    replace_str = payload.get('replace', '')
    ids = payload.get('ids') or []
    exact = bool(payload.get('exact'))

    if not ids or not find_str.strip():
        dlg.respond({'renamed': {}, 'conflicts': 0, 'failed': 0})
        return

    flags = 0 if exact else re.IGNORECASE
    find_re = re.compile(re.escape(find_str), flags)

    rename_pairs = []
    for id_str in ids:
        element = _elem_by_id.get(id_str)
        if element is None:
            continue
        old_name = _display_name(element)
        new_name = find_re.sub(replace_str, old_name)
        if new_name and new_name != old_name:
            rename_pairs.append((element, new_name))

    changes = {}
    conflicts = []
    failed = []
    if rename_pairs:
        # one undo step for the whole batch
        with revit.TransactionGroup('ReName', doc=_doc):
            renamed, conflicts, failed = _apply_renames(_doc, rename_pairs)
        _renamed.extend(renamed)
        _conflicts.extend(conflicts)
        _failed.extend(failed)
        get_elementid_value = get_elementid_value_func()
        for element, old_name, new_name in renamed:
            changes[str(get_elementid_value(element.Id))] = \
                [old_name, new_name]

    dlg.respond({
        'renamed': changes,
        'conflicts': len(conflicts),
        'failed': len(failed),
    })


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    global _doc, _target, _elem_by_id
    doc = revit.doc
    _doc = doc

    # 1) pick what to rename
    target = forms.CommandSwitchWindow.show(
        sorted(COLLECTORS.keys()),
        message='What do you want to rename?')
    if not target:
        return
    _target = target

    # 2) gather all items (id -> element, id -> name, id -> category)
    get_elementid_value = get_elementid_value_func()
    items = []
    for element in COLLECTORS[target](doc):
        if _target == 'Family Names':
            name = _family_name(element)
            cat_name = _family_category(element)
        else:
            name = revit.query.get_name(element)
            cat_name = ''
        if not name:
            continue
        id_str = str(get_elementid_value(element.Id))
        item = {'id': id_str, 'name': name}
        if cat_name:
            item['category'] = cat_name
        items.append(item)
        _elem_by_id[id_str] = element

    items.sort(key=lambda item: item['name'].lower())

    if not items:
        forms.alert('No {} found in the model.'.format(target.lower()),
                    title='ReName', exitscript=True)

    # 3) single form: live-filtered list + find/replace, inline results
    dlg = HtmlDialog(
        title='ReName - {}'.format(target),
        html='rename.html',
        data={'category': target, 'items': items},
    )
    dlg.register_module(globals())
    dlg.show()


if __name__ == '__main__':
    main()
