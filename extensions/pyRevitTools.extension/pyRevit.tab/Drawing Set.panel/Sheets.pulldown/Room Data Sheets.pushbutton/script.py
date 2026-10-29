# -*- coding: utf-8 -*-
"""Room Data Sheets - create a room's views and (optionally) a sheet.

Per room you can create any combination of:

  * a floor plan, rotated along the room's longest boundary
  * a reflected ceiling plan
  * four interior elevations (A-D)
  * two sections, one horizontal and one vertical to the plan view
  * an axonometric 3D view

and place them on a new sheet with the chosen titleblock, sheet number and
viewport type. View names can be prefixed.

Settings are collected with the shared ``uiUtils.html`` dialog, so the tool runs
on both pyRevit engines: IronPython 2.7 (Revit 2024) and CPython (Revit 2025+).
"""
from pyrevit import revit, DB, script

from uiUtils.html import HtmlDialog

import rdsUtils

# pyRevit keeps imported modules cached for the whole Revit session, so after the
# helper module is edited it would otherwise stay stale until Revit is restarted.
try:
    from importlib import reload as _reload_module
except ImportError:
    try:
        from imp import reload as _reload_module
    except ImportError:
        _reload_module = None

if _reload_module is not None:
    try:
        _reload_module(rdsUtils)
    except Exception:
        pass


output = script.get_output()
config = script.get_config()

VIEW_SCALE = rdsUtils.DEFAULT_VIEW_SCALE
ELEVATION_LABELS = ['A', 'B', 'C', 'D']
NONE_OPTION = '<None>'
TB_ORIENTATIONS = ['Vertical', 'Horizontal']
SECTION_NAMES = ['Horizontal', 'Vertical']

VIEW_FLAGS = ('create_plan', 'create_rcp', 'create_elevations',
              'create_sections', 'create_axo')


class SheetOptions(object):
    """Dialog values resolved to Revit objects and internal units."""

    def __init__(self):
        self.create_sheet = True
        self.sheet_number = '1000'
        self.titleblock_type = None
        self.viewport_type = None
        self.view_prefix = ''

        self.create_plan = True
        self.create_rcp = True
        self.create_elevations = True
        self.create_sections = False
        self.create_axo = False

        self.vt_plans = None
        self.vt_rcp = None
        self.vt_elevations = None
        self.vt_sections = None
        self.vt_axo = None

        self.elevation_type = None
        self.section_type = None

        self.crop_offset = 0.0
        self.titleblock_offset = 0.0
        self.tb_orientation = TB_ORIENTATIONS[0]
        self.floor_plan_type = None
        self.ceiling_plan_type = None
        self.view_scale = VIEW_SCALE


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _index_of(items, value, default=0):
    try:
        return items.index(value)
    except (ValueError, AttributeError):
        return default


def _payload_index(payload, key, count, default=0):
    try:
        index = int(payload.get(key, default))
    except (TypeError, ValueError):
        index = default
    return index if 0 <= index < count else default


def _item(items, index, default=None):
    if not items:
        return default
    if 0 <= index < len(items):
        return items[index]
    return items[0]


def room_name(room):
    param = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME)
    name = param.AsString() if param else None
    return name or 'Room'


def room_sheet_name(room):
    return '{} - {}'.format(room.Number, room_name(room))


def get_rooms(doc):
    """Rooms from the current selection, otherwise ask the user to pick some."""
    rooms = [element for element in revit.get_selection().elements
             if isinstance(element, DB.Architecture.Room)]
    if not rooms:
        picked = revit.pick_elements_by_category(
            DB.BuiltInCategory.OST_Rooms, 'Pick Rooms for Room Data Sheets')
        rooms = [element for element in (picked or [])
                 if isinstance(element, DB.Architecture.Room)]
    return rooms


# ---------------------------------------------------------------------------
# dialog
# ---------------------------------------------------------------------------
def gather_dialog_data(doc, rooms):
    """Collect everything the settings dialog needs and the stored defaults."""
    def titleblock_label(titleblock):
        return '{} : {}'.format(titleblock.FamilyName,
                                rdsUtils.type_name(titleblock))

    titleblock_types = sorted(rdsUtils.get_titleblock_types(doc),
                              key=titleblock_label)
    titleblock_names = [titleblock_label(titleblock)
                        for titleblock in titleblock_types]

    plan_templates = [NONE_OPTION] + rdsUtils.get_view_templates(doc, DB.ViewPlan)
    section_templates = [NONE_OPTION] + rdsUtils.get_view_templates(doc, DB.ViewSection)
    axo_templates = [NONE_OPTION] + rdsUtils.get_view_templates(doc, DB.View3D)

    viewport_types = sorted(
        rdsUtils.get_viewport_types(doc),
        key=lambda viewport_type: rdsUtils.type_name(viewport_type) or '')
    viewport_names = [rdsUtils.type_name(viewport_type) or ''
                      for viewport_type in viewport_types]

    elevation_types = rdsUtils.get_elevation_marker_types(doc)
    elevation_names = [rdsUtils.type_name(elevation_type) or ''
                       for elevation_type in elevation_types]

    section_types = rdsUtils.get_section_types(doc)
    section_names = [rdsUtils.type_name(section_type) or ''
                     for section_type in section_types]

    metric = rdsUtils.is_metric(doc)
    defaults = {
        'create_sheet': _as_bool(config.get_option('create_sheet', True)),
        'titleblock': _index_of(
            titleblock_names,
            config.get_option('titleblock',
                              titleblock_names[0] if titleblock_names else '')),
        'sheet_number': str(config.get_option('sheet_number', '1000')),
        'tb_orientation': _index_of(
            TB_ORIENTATIONS,
            config.get_option('titleblock_orientation', TB_ORIENTATIONS[0])),
        'view_prefix': str(config.get_option('view_prefix', '')),
        'create_plan': _as_bool(config.get_option('create_plan', True)),
        'create_rcp': _as_bool(config.get_option('create_rcp', True)),
        'create_elevations': _as_bool(config.get_option('create_elevations', True)),
        'create_sections': _as_bool(config.get_option('create_sections', False)),
        'create_axo': _as_bool(config.get_option('create_axo', False)),
        'vt_plans': _index_of(
            plan_templates, config.get_option('viewplan', NONE_OPTION)),
        'vt_rcp': _index_of(
            plan_templates, config.get_option('viewceiling', NONE_OPTION)),
        'vt_elevations': _index_of(
            section_templates, config.get_option('viewelevation', NONE_OPTION)),
        'vt_sections': _index_of(
            section_templates, config.get_option('viewsection', NONE_OPTION)),
        'vt_axo': _index_of(
            axo_templates, config.get_option('viewaxo', NONE_OPTION)),
        'viewport': _index_of(
            viewport_names, config.get_option('viewport',
                                              viewport_names[0] if viewport_names else '')),
        'elevation_type': _index_of(
            elevation_names, config.get_option('elevation_type', '')),
        'section_type': _index_of(
            section_names, config.get_option('section_type', '')),
    }

    dialog_data = {
        'room_count': len(rooms),
        'room_names': [room_sheet_name(room) for room in rooms[:200]],
        'titleblocks': titleblock_names,
        'plan_templates': plan_templates,
        'section_templates': section_templates,
        'axo_templates': axo_templates,
        'viewports': viewport_names,
        'elevation_types': elevation_names,
        'section_types': section_names,
        'tb_orientations': TB_ORIENTATIONS,
        'defaults': defaults,
    }
    # the objects behind the dialog lists, so payload indices resolve reliably
    # plus the offsets, which are fixed values (no longer exposed in the dialog)
    context = {
        'titleblock_types': titleblock_types,
        'viewport_types': viewport_types,
        'elevation_types': elevation_types,
        'section_types': section_types,
        'crop_offset': str(config.get_option(
            'crop_offset', '350' if metric else '9.0')),
        'titleblock_offset': str(config.get_option(
            'titleblock_offset', '165' if metric else '4.2')),
    }
    return dialog_data, context


def _template(doc, names, payload, key):
    return rdsUtils.get_view_template_by_name(
        doc, _item(names, _payload_index(payload, key, len(names))))


def resolve_options(doc, payload, dialog_data, context):
    """Turn the dialog payload back into Revit objects and internal units."""
    options = SheetOptions()

    options.create_sheet = _as_bool(payload.get('create_sheet', True))
    options.sheet_number = str(payload.get('sheet_number') or '').strip()
    if options.create_sheet and not options.sheet_number:
        raise rdsUtils.RdsError('A sheet number is required.')

    for flag in VIEW_FLAGS:
        setattr(options, flag, _as_bool(payload.get(flag, False)))
    if not any(getattr(options, flag) for flag in VIEW_FLAGS):
        raise rdsUtils.RdsError('Select at least one view to create.')

    options.view_prefix = str(payload.get('view_prefix') or '').strip()

    if options.create_sheet:
        titleblock_names = dialog_data['titleblocks']
        options.titleblock_type = _item(
            context['titleblock_types'],
            _payload_index(payload, 'titleblock', len(titleblock_names)))
        if options.titleblock_type is None:
            raise rdsUtils.RdsError('There are no titleblocks in the model.')

        viewport_names = dialog_data['viewports']
        options.viewport_type = _item(
            context['viewport_types'],
            _payload_index(payload, 'viewport', len(viewport_names)))
        if options.viewport_type is None:
            raise rdsUtils.RdsError('There are no viewport types in the model.')

    plan_templates = dialog_data['plan_templates']
    section_templates = dialog_data['section_templates']
    axo_templates = dialog_data['axo_templates']
    options.vt_plans = _template(doc, plan_templates, payload, 'vt_plans')
    options.vt_rcp = _template(doc, plan_templates, payload, 'vt_rcp')
    options.vt_elevations = _template(doc, section_templates, payload, 'vt_elevations')
    options.vt_sections = _template(doc, section_templates, payload, 'vt_sections')
    options.vt_axo = _template(doc, axo_templates, payload, 'vt_axo')

    if options.create_elevations:
        elevation_types = context['elevation_types']
        options.elevation_type = _item(
            elevation_types,
            _payload_index(payload, 'elevation_type', len(elevation_types)))
        if options.elevation_type is None:
            raise rdsUtils.RdsError('There are no interior elevation types '
                                    'in the model.')

    if options.create_sections:
        section_types = context['section_types']
        options.section_type = _item(
            section_types,
            _payload_index(payload, 'section_type', len(section_types)))
        if options.section_type is None:
            raise rdsUtils.RdsError('There are no section types in the model.')

    options.crop_offset = rdsUtils.to_internal_length(context['crop_offset'], doc)
    options.titleblock_offset = rdsUtils.to_internal_length(
        context['titleblock_offset'], doc)
    options.tb_orientation = _item(
        TB_ORIENTATIONS,
        _payload_index(payload, 'tb_orientation', len(TB_ORIENTATIONS)))

    if options.create_plan or options.create_elevations:
        floor_plan_types = rdsUtils.get_view_family_types(DB.ViewFamily.FloorPlan, doc)
        if not floor_plan_types:
            raise rdsUtils.RdsError('The model needs a floor plan view type.')
        options.floor_plan_type = floor_plan_types[0]

    if options.create_rcp:
        ceiling_plan_types = rdsUtils.get_view_family_types(
            DB.ViewFamily.CeilingPlan, doc)
        if not ceiling_plan_types:
            raise rdsUtils.RdsError('The model needs a ceiling plan view type.')
        options.ceiling_plan_type = ceiling_plan_types[0]

    return options


def save_defaults(payload):
    """Remember the dialog values for the next run."""
    config.set_option('create_sheet', _as_bool(payload.get('create_sheet')))
    config.set_option('sheet_number', str(payload.get('sheet_number') or ''))
    config.set_option('view_prefix', str(payload.get('view_prefix') or ''))
    for flag in VIEW_FLAGS:
        config.set_option(flag, _as_bool(payload.get(flag)))

    titleblock_names = _dialog_data['titleblocks']
    config.set_option('titleblock', _item(
        titleblock_names,
        _payload_index(payload, 'titleblock', len(titleblock_names)), ''))
    config.set_option('titleblock_orientation', _item(
        TB_ORIENTATIONS,
        _payload_index(payload, 'tb_orientation', len(TB_ORIENTATIONS))))

    for payload_key, option_name, values_key in (
            ('vt_plans', 'viewplan', 'plan_templates'),
            ('vt_rcp', 'viewceiling', 'plan_templates'),
            ('vt_elevations', 'viewelevation', 'section_templates'),
            ('vt_sections', 'viewsection', 'section_templates'),
            ('vt_axo', 'viewaxo', 'axo_templates'),
            ('viewport', 'viewport', 'viewports'),
            ('elevation_type', 'elevation_type', 'elevation_types'),
            ('section_type', 'section_type', 'section_types')):
        values = _dialog_data[values_key]
        config.set_option(option_name,
                          _item(values,
                                _payload_index(payload, payload_key, len(values)),
                                ''))

    script.save_config()


# ---------------------------------------------------------------------------
# view creation
# ---------------------------------------------------------------------------
def require_elevation_type_template(doc, options):
    """Un-hide rooms in the elevation type's default template if necessary.

    Returns False when the user declines to remove the hiding template.
    """
    if not options.create_elevations:
        return True
    template = doc.GetElement(options.elevation_type.DefaultTemplateId)
    if template is None:
        return True
    rooms_category = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Rooms)
    if not template.GetCategoryHidden(rooms_category.Id):
        return True
    if not rdsUtils.confirm(
            'To create the elevations the default view template of the '
            'elevation type has to stop hiding rooms. Remove it?'):
        return False
    with revit.Transaction('Remove View Template', doc):
        options.elevation_type.DefaultTemplateId = DB.ElementId(-1)
    return True


def _create_plan_views(doc, options, room, angle):
    """Create the requested plan, RCP and axo views (None when not requested)."""
    view_plan = None
    view_rcp = None
    view_axo = None
    with revit.Transaction('Create Views', doc):
        if options.create_plan or options.create_elevations:
            # a plan view is also the host of the elevation markers
            view_plan = DB.ViewPlan.Create(
                doc, options.floor_plan_type.Id, room.Level.Id)
            view_plan.Scale = options.view_scale
        if options.create_rcp:
            view_rcp = DB.ViewPlan.Create(
                doc, options.ceiling_plan_type.Id, room.Level.Id)
            view_rcp.Scale = options.view_scale
        if options.create_axo:
            view_axo = rdsUtils.create_room_axo_rotate(
                room, angle, options.view_scale, doc)
    return view_plan, view_rcp, view_axo


def _crop_plans(doc, options, room, angle, views):
    """Rotate and crop the plan views to the room boundary."""
    views = [view for view in views if view is not None]
    if not views:
        return

    pairs = [(view, rdsUtils.find_crop_box(doc, view)) for view in views]
    if any(crop_box is None for _, crop_box in pairs):
        raise rdsUtils.RdsError('Could not find the crop box of the new plan views.')

    with revit.Transaction('Crop Plans', doc):
        axis = rdsUtils.get_bb_axis_in_view(room, views[0])
        for view, crop_box in pairs:
            DB.ElementTransformUtils.RotateElement(doc, crop_box.Id, axis, angle)
            view.CropBoxActive = True
        doc.Regenerate()

        room_boundaries = rdsUtils.get_room_bound(room)
        if not room_boundaries:
            return
        try:
            # offset the boundaries so the walls show up in the plan
            offset_loop = DB.CurveLoop.CreateViaOffset(
                room_boundaries, options.crop_offset, DB.XYZ(0, 0, 1))
        except Exception:
            # some shapes cannot be offset - fall back to the bounding box
            outline = rdsUtils.room_bb_outlines(room, angle)
            offset_loop = DB.CurveLoop.CreateViaOffset(
                outline, options.crop_offset, DB.XYZ.BasisZ)
        for view, _ in pairs:
            view.GetCropRegionShapeManager().SetCropShape(offset_loop)


def _create_elevations(doc, options, room, angle, host_plan, view_base):
    """Four interior elevations around the room, returns [(view, label)]."""
    marker = DB.ElevationMarker.CreateElevationMarker(
        doc, options.elevation_type.Id, room.Location.Point, options.view_scale)
    elevations = []
    for index in range(4):
        elevations.append(marker.CreateElevation(doc, host_plan.Id, index))

    # align the marker with the room rotation
    doc.Regenerate()
    marker.Location.Rotate(
        DB.Line.CreateBound(room.Location.Point,
                            room.Location.Point + DB.XYZ.BasisZ), angle)
    doc.Regenerate()

    results = []
    for view, label in zip(elevations, ELEVATION_LABELS):
        view.Scale = options.view_scale
        view.Name = rdsUtils.unique_view_name(
            view_base, ' Elevation ' + label, doc)
        rdsUtils.set_anno_crop(view)
        results.append((view, label))
    return results


def _create_sections(doc, options, room, angle, view_base):
    """Two sections through the room centre: horizontal and vertical."""
    sections = []
    for line, name in zip(rdsUtils.section_axes(room, angle), SECTION_NAMES):
        section_box = rdsUtils.create_parallel_bbox(line, room)
        view = DB.ViewSection.CreateSection(
            doc, options.section_type.Id, section_box)
        view.Scale = options.view_scale
        view.Name = rdsUtils.unique_view_name(
            view_base, ' Section ' + name, doc)
        rdsUtils.set_anno_crop(view)
        sections.append(view)
    return sections


def create_room_data_sheet(doc, options, room):
    """Create the requested views for a room and place them on a new sheet."""
    if room.Location is None or room.Level is None:
        raise rdsUtils.RdsError('Room is not placed.')

    sheet_name = room_sheet_name(room)
    view_base = (options.view_prefix or '') + sheet_name
    angle = rdsUtils.room_rotation_angle(room)

    view_plan, view_rcp, view_axo = _create_plan_views(doc, options, room, angle)

    with revit.Transaction('Name Views', doc):
        if view_plan is not None:
            view_plan.Name = rdsUtils.unique_view_name(view_base, ' Plan', doc)
            rdsUtils.set_anno_crop(view_plan)
        if view_rcp is not None:
            view_rcp.Name = rdsUtils.unique_view_name(
                view_base, ' Reflected Ceiling Plan', doc)
            rdsUtils.set_anno_crop(view_rcp)
        if view_axo is not None:
            view_axo.Name = rdsUtils.unique_view_name(
                view_base, ' Axonometric', doc)

    _crop_plans(doc, options, room, angle, [view_plan, view_rcp])

    placements = []
    if options.create_plan and view_plan is not None:
        placements.append((view_plan, None))
    if options.create_rcp and view_rcp is not None:
        placements.append((view_rcp, None))
    if options.create_axo and view_axo is not None:
        placements.append((view_axo, None))

    elevations = []
    sections = []
    with revit.Transaction('Create Elevations and Sections', doc):
        if options.create_elevations:
            elevations = _create_elevations(
                doc, options, room, angle, view_plan, view_base)
            placements.extend(elevations)
        if options.create_sections:
            sections = _create_sections(doc, options, room, angle, view_base)
            placements.extend((view, None) for view in sections)

    with revit.Transaction('Prepare Views', doc):
        for view, _ in elevations:
            rdsUtils.set_crop_to_bb(room, view, options.crop_offset, doc)
        for view in sections:
            rdsUtils.set_crop_to_bb(room, view, options.crop_offset, doc)

        rdsUtils.apply_view_template(view_plan, options.vt_plans)
        rdsUtils.apply_view_template(view_rcp, options.vt_rcp)
        rdsUtils.apply_view_template(view_axo, options.vt_axo)
        for view, _ in elevations:
            rdsUtils.apply_view_template(view, options.vt_elevations)
        for view in sections:
            rdsUtils.apply_view_template(view, options.vt_sections)

    sheet = None
    if options.create_sheet:
        with revit.Transaction('Create Sheet', doc):
            sheet = rdsUtils.create_sheet(
                options.sheet_number, sheet_name, options.titleblock_type.Id, doc)

        positions = rdsUtils.sheet_grid_positions(
            sheet, options.titleblock_offset, options.tb_orientation,
            len(placements))
        placed = []
        with revit.Transaction('Add Views to Sheet', doc):
            for (view, label), position in zip(placements, positions):
                viewport = DB.Viewport.Create(doc, sheet.Id, view.Id, position)
                if label:
                    detail_number = viewport.get_Parameter(
                        DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
                    if detail_number:
                        detail_number.Set(label)
                placed.append(viewport)
            doc.Regenerate()
            for viewport in placed:
                try:
                    viewport.ChangeTypeId(options.viewport_type.Id)
                except Exception:
                    pass
            doc.Regenerate()
            rdsUtils.realign_pos(doc, placed, positions)

    return sheet, sheet_name


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
_dialog_data = {}


def main():
    global _dialog_data

    doc = revit.doc

    rooms = get_rooms(doc)
    if not rooms:
        print('No rooms selected - nothing to do.')
        return

    _dialog_data, context = gather_dialog_data(doc, rooms)
    if not _dialog_data['elevation_types'] and not _dialog_data['section_types']:
        rdsUtils.alert('No elevation or section types are available in the model.')
        return

    dialog = HtmlDialog(
        title='Room Data Sheets',
        html='room_data_sheets.html',
        data=_dialog_data,
        width=780,
        height=760)
    payload = dialog.show()
    if not payload:
        return

    try:
        options = resolve_options(doc, payload, _dialog_data, context)
    except rdsUtils.RdsError as error:
        rdsUtils.alert(str(error))
        return

    save_defaults(payload)
    if not require_elevation_type_template(doc, options):
        return

    created = 0
    failures = []
    for room in rooms:
        try:
            sheet, sheet_name = create_room_data_sheet(doc, options, room)
        except Exception as error:
            failures.append((room, str(error)))
            print('Room {}: FAILED - {}'.format(room.Number, error))
            continue
        created += 1
        if sheet is None:
            print('Views created for room {}'.format(sheet_name))
        else:
            print('Sheet: {}\tRoom {}'.format(output.linkify(sheet.Id), sheet_name))

    if failures:
        print('')
        print('{} of {} rooms failed: {}'.format(
            len(failures), len(rooms),
            ', '.join('{} ({})'.format(room.Number, message)
                      for room, message in failures)))
    if created:
        print('')
        if options.create_sheet:
            print('{} sheet(s) created.'.format(created))
        else:
            print('Views created for {} room(s) - no sheets were created.'
                  .format(created))


if __name__ == '__main__':
    try:
        main()
    except rdsUtils.RdsError as err:
        rdsUtils.alert(str(err))
    except Exception as err:
        import traceback
        traceback.print_exc()
        rdsUtils.alert('Room Data Sheets failed:\n{}'.format(err))
