# -*- coding: utf-8 -*-
"""Find and wipe project parameters that have no value on any element.

For each project parameter (shared + non-shared), this tool runs a native
'has value' filter over the whole document using
ParameterFilterRuleFactory.CreateHasValueParameterRule + ElementParameterFilter.
If no element (instance OR element type) passes the filter AND at least one
bound category contains elements, the parameter is reported as UNUSED.

You can then multi-select the unused parameters to remove their bindings.

Works on Revit 2022+.
"""

from pyrevit import forms, revit, DB
from pyrevit import HOST_APP
from pyrevit import script
from pyrevit.compat import get_elementid_value_func

logger = script.get_logger()
# TEMP DISABLED (A/B test): re-enable to restore the output-window report.
# output = script.get_output()

get_elementid_value = get_elementid_value_func()

doc = revit.doc


def _safe(text):
    """ASCII-safe string (protects IronPython 2.7 output from unicode errors)."""
    if text is None:
        return ''
    return text.encode('ascii', 'replace').decode('ascii')


def _collect_shared_param_ids():
    """Map shared parameter GUID string -> parameter ElementId."""
    guid_map = {}
    try:
        for spe in DB.FilteredElementCollector(doc).OfClass(DB.SharedParameterElement):
            try:
                guid_map[str(spe.GuidValue).lower()] = spe.Id
            except Exception:
                continue
    except Exception:
        pass
    return guid_map


def _get_param_id(p, shared_guid_map):
    """Resolve the parameter ElementId for a BindingMap definition key."""
    # InternalDefinition (non-shared project params) exposes .Id (Revit 2022+)
    try:
        return p.Id
    except AttributeError:
        pass
    # ExternalDefinition (shared params): resolve GUID via SharedParameterElement
    try:
        return shared_guid_map.get(str(p.GUID).lower())
    except Exception:
        return None


def _data_type_label(p):
    """Version-aware data type label for display."""
    try:
        if HOST_APP.is_newer_than(2022, or_equal=True):
            return str(p.GetDataType().TypeId)
        return str(p.UnitType)
    except Exception:
        return '-'


def _collect_filter_used_param_ids():
    """Return set of parameter id values referenced by any view filter rule.

    A parameter with no element values can still be referenced by a view
    filter (e.g. a 'has value' filter currently matching nothing). Such
    parameters are reported as IN USE so they are not wiped by accident.
    """
    used = set()

    def add_rules(efilter):
        if efilter is None:
            return
        try:
            if isinstance(efilter, DB.ElementParameterFilter):
                for rule in efilter.GetRules():
                    try:
                        used.add(get_elementid_value(rule.GetRuleParameter()))
                    except Exception:
                        pass
            elif isinstance(efilter, (DB.LogicalAndFilter, DB.LogicalOrFilter)):
                for sub in efilter.GetFilters():
                    add_rules(sub)
        except Exception:
            pass

    try:
        for fe in DB.FilteredElementCollector(doc).OfClass(DB.ParameterFilterElement):
            try:
                add_rules(fe.GetElementFilter())
            except Exception:
                continue
    except Exception:
        pass
    return used


cat_has_any_cache = {}


def _category_has_any(cat_id):
    """Return True if the given category contains at least one element.

    Result is cached per category (the set of distinct categories is small),
    and uses FirstElement() so the scan stops at the first hit.
    """
    key = get_elementid_value(cat_id)
    if key not in cat_has_any_cache:
        try:
            cat_has_any_cache[key] = \
                DB.FilteredElementCollector(doc).OfCategoryId(cat_id).FirstElement() is not None
        except Exception:
            cat_has_any_cache[key] = False  # cannot verify -> treat as unverifiable
    return cat_has_any_cache[key]


def main():
    if doc.IsFamilyDocument:
        forms.alert('This tool is for project documents only.',
                    exitscript=True)

    pm = doc.ParameterBindings
    shared_guid_map = _collect_shared_param_ids()
    filter_used_ids = _collect_filter_used_param_ids()

    it = pm.ForwardIterator()
    it.Reset()

    records = []   # ordered list of report dicts
    seen = {}      # parameter id value -> rec (dedupe shared params)

    while it.MoveNext():
        p = it.Key
        b = pm[p]

        if isinstance(b, DB.InstanceBinding):
            bind = 'Instance'
        elif isinstance(b, DB.TypeBinding):
            bind = 'Type'
        else:
            bind = 'Unknown'

        name = _safe(p.Name)
        param_id = _get_param_id(p, shared_guid_map)
        pid_val = get_elementid_value(param_id) if param_id is not None else None

        # dedupe: a shared param bound to multiple groups shows up repeatedly
        if pid_val is not None and pid_val in seen:
            rec = seen[pid_val]
            rec['cats'] |= set(_safe(cat.Name) for cat in b.Categories)
            if bind == 'Type':
                rec['bind'] = 'Type'
            continue

        rec = {
            'name': name,
            'bind': bind,
            'cats': set(_safe(cat.Name) for cat in b.Categories),
            'datatype': _safe(_data_type_label(p)),
            'status': 'UNKNOWN',
            'note': '',
            'definition': p,
        }
        if pid_val is not None:
            seen[pid_val] = rec

        if param_id is None:
            rec['status'] = 'UNVERIFIABLE'
            rec['note'] = 'could not resolve parameter id'
            records.append(rec)
            continue

        # build the native 'has value' filter
        try:
            rule = DB.ParameterFilterRuleFactory.CreateHasValueParameterRule(param_id)
            param_filter = DB.ElementParameterFilter(rule)
        except Exception as exc:
            rec['status'] = 'UNVERIFIABLE'
            rec['note'] = 'rule creation failed: {}'.format(_safe(str(exc)))
            records.append(rec)
            continue

        # single doc-wide pass, early-exit at the first match. the plain
        # collector includes element types, so this covers BOTH instance-bound
        # and type-bound values in one scan (types are included by default).
        try:
            first_match = DB.FilteredElementCollector(doc) \
                            .WherePasses(param_filter) \
                            .FirstElement()
        except Exception as exc:
            rec['status'] = 'UNVERIFIABLE'
            rec['note'] = 'filter failed: {}'.format(_safe(str(exc)))
            records.append(rec)
            continue

        if first_match is not None:
            rec['status'] = 'IN USE'
        elif pid_val in filter_used_ids:
            rec['status'] = 'IN USE'
            rec['note'] = 'referenced by view filter'
        else:
            # confirm at least one bound category actually contains elements
            has_elements = False
            for cat in b.Categories:
                if _category_has_any(cat.Id):
                    has_elements = True
                    break
            if not has_elements:
                rec['status'] = 'UNVERIFIABLE'
                rec['note'] = 'no elements in bound categories'
            else:
                rec['status'] = 'UNUSED'
        records.append(rec)

    unused_params = [rec for rec in records if rec['status'] == 'UNUSED']

    if not unused_params:
        forms.alert('No unused project parameters found. Nothing to wipe.',
                    exitscript=True)

    # ------------------------------------------------------------------
    # select + purge
    # ------------------------------------------------------------------
    class ParamToPurge(forms.TemplateListItem):
        @property
        def name(self):
            return self.item['name']

    return_options = forms.SelectFromList.show(
        [ParamToPurge(x) for x in unused_params],
        title='Select Unused Parameters to Wipe ({})'.format(len(unused_params)),
        width=600,
        button_name='Wipe Parameters',
        multiselect=True
    )

    if return_options:
        with revit.Transaction('Wipe Unused Project Parameters'):
            for pp in return_options:
                try:
                    if pm.Remove(pp['definition']):
                        logger.debug('Removed parameter: {}'.format(pp['name']))
                    else:
                        logger.warning('Could not remove parameter: {}'.format(pp['name']))
                except Exception as del_err:
                    logger.error('Error removing parameter: {} | {}'
                                 .format(pp['name'], del_err))
        forms.alert('Done. Removed {} parameter binding(s).'.format(len(return_options)),
                    exitscript=True)


if __name__ == '__main__':
    main()
