# -*- coding: utf-8 -*-
"""Select elements with a manual graphic override.

Finds every element that carries an element-level graphic override
("Override Graphics in View > By Element") in the active view and puts those
elements into the current selection.

Revit stores overrides per view.  View.GetElementOverrides() always returns
settings - for an element that was never overridden they match a brand-new
OverrideGraphicSettings() - so an element counts as overridden when any
channel differs from a default instance.

Only element-level overrides are found; category overrides and view-filter
overrides are separate mechanisms.  Only elements visible in the active view
are scanned, and an override deliberately set to its default value (e.g.
transparency 0) cannot be told apart from one that was never set.

Works on Revit 2022+.
"""

from pyrevit import revit, DB
from pyrevit import script
from pyrevit.compat import get_elementid_value_func

output = script.get_output()
get_elementid_value = get_elementid_value_func()

# every channel on OverrideGraphicSettings that an override can set
OVERRIDE_CHANNELS = (
    'ProjectionLineColor',
    'ProjectionLinePatternId',
    'ProjectionLineWeight',
    'CutLineColor',
    'CutLinePatternId',
    'CutLineWeight',
    'SurfaceForegroundPatternId',
    'SurfaceForegroundPatternColor',
    'SurfaceBackgroundPatternId',
    'SurfaceBackgroundPatternColor',
    'CutForegroundPatternId',
    'CutForegroundPatternColor',
    'CutBackgroundPatternId',
    'CutBackgroundPatternColor',
    'SurfaceTransparency',
    'Halftone',
)

MAX_REPORT_ROWS = 50


def _safe(text):
    """ASCII-safe string (protects IronPython 2.7 output from unicode errors)."""
    if text is None:
        return ''
    return text.encode('ascii', 'replace').decode('ascii')


def _comparable(value):
    """Normalised channel value: colours by RGB, element ids by integer."""
    if isinstance(value, DB.Color):
        return (value.Red, value.Green, value.Blue) if value.IsValid else None
    if isinstance(value, DB.ElementId):
        return get_elementid_value(value)
    return value


def is_overridden(settings, default):
    """True when any override channel differs from the default settings."""
    for channel in OVERRIDE_CHANNELS:
        try:
            if _comparable(getattr(settings, channel)) != \
                    _comparable(getattr(default, channel)):
                return True
        except Exception:
            continue
    return False


def element_label(element):
    """Return a 'Category | Name' label for the report."""
    try:
        if element.Category is not None:
            return _safe('{} | {}'.format(element.Category.Name,
                                          element.Name))
        return _safe(element.Name)
    except Exception:
        return '(unknown element)'


def find_overridden(doc, view):
    """Return the elements in *view* that carry a manual graphic override."""
    default = DB.OverrideGraphicSettings()
    overridden = []

    elements = DB.FilteredElementCollector(doc, view.Id)\
                 .WhereElementIsNotElementType()

    for element in elements:
        try:
            settings = view.GetElementOverrides(element.Id)
        except Exception:
            continue
        if is_overridden(settings, default):
            overridden.append(element)

    return overridden


def report(view, overridden):
    output.print_md('### Select Elements with Manual Override')
    output.print_md('View: **{}**'.format(_safe(view.Name)))

    if not overridden:
        output.print_md('No overridden elements found.')
        return

    for element in overridden[:MAX_REPORT_ROWS]:
        output.print_md('* {} - {}'.format(output.linkify(element.Id),
                                           element_label(element)))

    if len(overridden) > MAX_REPORT_ROWS:
        output.print_md('... and {} more not shown'
                        .format(len(overridden) - MAX_REPORT_ROWS))


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    if doc is None or uidoc is None:
        output.print_md('No active document.')
        return

    if doc.IsFamilyDocument:
        output.print_md('This tool works on project documents only.')
        return

    view = uidoc.ActiveGraphicalView
    if view is None:
        output.print_md('Open a graphical view (plan, section, elevation, '
                        '3D, detail or legend) and run the tool again.')
        return

    overridden = find_overridden(doc, view)
    report(view, overridden)

    if not overridden:
        return

    revit.get_selection().set_to([element.Id for element in overridden])
    output.print_md('**Selected {} element(s).**'.format(len(overridden)))


if __name__ == '__main__':
    main()
