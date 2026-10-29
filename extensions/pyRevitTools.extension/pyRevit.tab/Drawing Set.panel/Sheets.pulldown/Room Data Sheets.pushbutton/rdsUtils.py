# -*- coding: utf-8 -*-
"""Helper library for the Room Data Sheets tool.

Units, view and sheet helpers, room geometry and the sheet layout maths used by
the button. Only the Revit API and pyrevit are used, so the module runs on both
pyRevit engines:

  * IronPython 2.7 - Revit 2024 and earlier
  * CPython        - Revit 2025 / 2026 (pythonnet)
"""
import math
import re

import clr  # noqa: F401

clr.AddReference('System')
clr.AddReference('System.Windows.Forms')

from System.Collections.Generic import List  # noqa: E402,F401
from System.Windows.Forms import DialogResult  # noqa: E402
from System.Windows.Forms import (  # noqa: E402
    MessageBox, MessageBoxButtons, MessageBoxIcon)

from pyrevit import revit, DB, coreutils  # noqa: E402

DEFAULT_VIEW_SCALE = 50


class RdsError(Exception):
    """Recoverable Room Data Sheets failure."""


def alert(message, title='Room Data Sheets'):
    """Show a blocking message box (engine agnostic stand-in for forms.alert)."""
    MessageBox.Show(message, title, MessageBoxButtons.OK, MessageBoxIcon.Warning)


def confirm(message, title='Room Data Sheets'):
    """Ask a yes/no question and return True when the user accepts."""
    result = MessageBox.Show(message, title,
                             MessageBoxButtons.YesNo, MessageBoxIcon.Question)
    return result == DialogResult.Yes


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------
def is_metric(doc):
    return doc.DisplayUnitSystem == DB.DisplayUnit.METRIC


def length_unit(doc):
    return doc.GetUnits().GetFormatOptions(DB.SpecTypeId.Length).GetUnitTypeId()


def to_internal_length(value, doc):
    """Convert a value typed in project display units into Revit internal units."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        match = re.search(r'[0-9]*\.?[0-9]+', str(value))
        if not match:
            raise RdsError('"{}" is not a valid length.'.format(value))
        number = float(match.group(0))
    return DB.UnitUtils.ConvertToInternalUnits(number, length_unit(doc))


# ---------------------------------------------------------------------------
# elements, views and sheets
# ---------------------------------------------------------------------------
def type_name(element_type):
    param = element_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if param and param.HasValue:
        return param.AsString()
    return None


def get_view_family_types(view_family, doc):
    return [view_type for view_type
            in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
            if view_type.ViewFamily == view_family]


def get_elevation_marker_types(doc):
    """Interior elevation types that can host a 4-sided elevation marker.

    Each candidate type is probed by creating a throw-away marker; the probing
    transaction is rolled back so the document is left untouched.
    """
    valid_types = []
    origin = DB.XYZ(0, 0, 0)
    transaction = DB.Transaction(doc, 'Test Elevation Marker Types')
    transaction.Start()
    try:
        for elevation_type in get_view_family_types(DB.ViewFamily.Elevation, doc):
            try:
                marker = DB.ElevationMarker.CreateElevationMarker(
                    doc, elevation_type.Id, origin, DEFAULT_VIEW_SCALE)
                if marker.MaximumViewCount == 4:
                    valid_types.append(elevation_type)
                doc.Delete(marker.Id)
            except Exception:
                continue
    finally:
        try:
            transaction.RollBack()
        except Exception:
            pass
    return valid_types


def get_section_types(doc):
    return get_view_family_types(DB.ViewFamily.Section, doc)


def get_titleblock_types(doc):
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                .WhereElementIsElementType()
                .ToElements())


def get_viewport_types(doc):
    viewport_types = list(DB.FilteredElementCollector(doc)
                          .OfCategory(DB.BuiltInCategory.OST_Viewports)
                          .WhereElementIsElementType()
                          .ToElements())
    if not viewport_types:
        existing = DB.FilteredElementCollector(doc).OfClass(DB.Viewport).FirstElement()
        if existing is not None:
            viewport_types = [doc.GetElement(type_id)
                              for type_id in existing.GetValidTypes()
                              if doc.GetElement(type_id) is not None]
    return viewport_types


def get_view_templates(doc, view_class):
    """Sorted names of the view templates of a given view class."""
    names = set()
    for view in DB.FilteredElementCollector(doc).OfClass(view_class):
        if view.IsTemplate:
            names.add(view.Name)
    return sorted(names)


def get_view_template_by_name(doc, name):
    if not name or name == '<None>':
        return None
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.IsTemplate and view.Name == name:
            return view
    return None


def get_view_by_name(doc, name):
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.Name == name:
            return view
    return None


def unique_view_name(name, suffix=None, doc=None):
    doc = doc or revit.doc
    unique_name = '{}{}'.format(name, suffix or '')
    while get_view_by_name(doc, unique_name):
        unique_name += ' Copy 1'
    return unique_name


def unique_sheet_name(name, doc=None, exclude_id=None):
    doc = doc or revit.doc
    existing = set(sheet.Name
                   for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                   if exclude_id is None or sheet.Id != exclude_id)
    unique_name = name
    while unique_name in existing:
        unique_name += ' Copy 1'
    return unique_name


def sheet_number_in_use(number, doc=None):
    doc = doc or revit.doc
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        if sheet.SheetNumber == number:
            return True
    return False


def create_sheet(sheet_number, sheet_name, titleblock_type_id, doc=None):
    doc = doc or revit.doc
    sheet_number = str(sheet_number)
    sheet = DB.ViewSheet.Create(doc, titleblock_type_id)
    sheet.Name = unique_sheet_name(sheet_name, doc, sheet.Id)
    while sheet_number_in_use(sheet_number, doc):
        sheet_number = coreutils.increment_str(sheet_number, 1)
    sheet.SheetNumber = sheet_number
    return sheet


def set_anno_crop(view):
    param = view.get_Parameter(DB.BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
    if param:
        param.Set(1)


def apply_view_template(view, view_template):
    if view is not None and view_template:
        view.ViewTemplateId = view_template.Id


# ---------------------------------------------------------------------------
# room geometry
# ---------------------------------------------------------------------------
def _point_equal_list(point, points):
    for candidate in list(points):
        if point.IsAlmostEqualTo(candidate, 0.003):
            return candidate
    return None


def _get_open_ends(curves):
    """Return the unmatched end points of a curve list (None when it is closed)."""
    endpoints = []
    for curve in curves:
        for index in range(2):
            duplicate = _point_equal_list(curve.GetEndPoint(index), endpoints)
            if duplicate is not None:
                endpoints.remove(duplicate)
            else:
                endpoints.append(curve.GetEndPoint(index))
    return endpoints or None


def get_room_bound(room):
    """Outer boundary of a room as a CurveLoop (None if the loop is open)."""
    segments = room.GetBoundarySegments(DB.SpatialElementBoundaryOptions())
    if not segments:
        return None
    curves = [segment.GetCurve() for segment in segments[0]]
    if _get_open_ends(curves):
        return None
    room_boundaries = DB.CurveLoop()
    for curve in curves:
        try:
            room_boundaries.Append(curve)
        except Exception:
            return None
    return room_boundaries


def get_longest_boundary(room):
    """Longest straight boundary of a room (used as its rotation reference)."""
    longest = None
    for loop in room.GetBoundarySegments(DB.SpatialElementBoundaryOptions()):
        for segment in loop:
            curve = segment.GetCurve()
            if not isinstance(curve, DB.Line):
                continue
            if longest is None or curve.Length > longest.Length:
                longest = curve
    return longest


def room_rotation_angle(room):
    """Angle between the room's longest boundary and the Y axis, clamped to +-90."""
    longest_boundary = get_longest_boundary(room)
    if longest_boundary is None:
        raise RdsError('Room {} has no straight boundary to rotate the view by.'
                       .format(room.Number))
    vector = longest_boundary.GetEndPoint(1) - longest_boundary.GetEndPoint(0)

    location = room.Location.Point
    y_direction = DB.XYZ(location.X, location.Y + 1, location.Z) - location

    angle = vector.AngleTo(y_direction)

    # pick the sign that actually rotates the vector onto the Y axis
    rotation = DB.Transform.CreateRotation(DB.XYZ.BasisZ, -angle)
    if round(math.degrees(rotation.OfVector(vector).AngleTo(y_direction)), 0) != 0:
        angle = -angle
        rotation = DB.Transform.CreateRotation(DB.XYZ.BasisZ, -angle)
        if round(math.degrees(rotation.OfVector(vector).AngleTo(y_direction)), 0) != 0:
            angle = math.radians(90) - angle

    while abs(angle) > math.radians(90):
        if angle > 0:
            angle = angle - math.radians(90)
        else:
            angle = angle + math.radians(90)
    return angle


def get_bb_outline(bounding_box):
    r1 = DB.XYZ(bounding_box.Min.X, bounding_box.Min.Y, bounding_box.Min.Z)
    r2 = DB.XYZ(bounding_box.Max.X, bounding_box.Min.Y, bounding_box.Min.Z)
    r3 = DB.XYZ(bounding_box.Max.X, bounding_box.Max.Y, bounding_box.Min.Z)
    r4 = DB.XYZ(bounding_box.Min.X, bounding_box.Max.Y, bounding_box.Min.Z)
    return [DB.Line.CreateBound(r1, r2),
            DB.Line.CreateBound(r2, r3),
            DB.Line.CreateBound(r3, r4),
            DB.Line.CreateBound(r4, r1)]


def _get_aligned_crop(geometry, transform):
    rotated_geometry = geometry.GetTransformed(transform)
    bb_outline = get_bb_outline(rotated_geometry.GetBoundingBox())
    rotate_back = transform.Inverse
    curves = [curve.CreateTransformed(rotate_back) for curve in bb_outline]
    return DB.CurveLoop.Create(List[DB.Curve](curves))


def room_bb_outlines(room, angle=None):
    """Room bounding-box outline, aligned with the room's longest boundary."""
    if angle is None:
        angle = room_rotation_angle(room)
    rotation = DB.Transform.CreateRotationAtPoint(
        DB.XYZ.BasisZ, angle, room.Location.Point)
    return _get_aligned_crop(room.ClosedShell, rotation.Inverse)


def section_axes(room, angle=None):
    """The two centre lines of the room's aligned bounding box.

    Returns ``(horizontal, vertical)``: the first line runs along the box's X
    axis, the second along its Y axis, both through the box centre, so the
    sections cut the room in half across each direction.
    """
    outline = room_bb_outlines(room, angle)
    edges = list(outline)
    if len(edges) < 3:
        raise RdsError('Could not read the room outline to place the sections.')

    first, second, opposite = edges[0], edges[1], edges[2]
    center = (first.GetEndPoint(0) + first.GetEndPoint(1)
              + opposite.GetEndPoint(0) + opposite.GetEndPoint(1)) * 0.25

    def centered(edge):
        half = (edge.GetEndPoint(1) - edge.GetEndPoint(0)) * 0.5
        return DB.Line.CreateBound(center - half, center + half)

    return centered(first), centered(second)


def create_parallel_bbox(line, crop_element, offset=300 / 304.8):
    """Section bounding box running parallel to a room boundary line."""
    start = line.GetEndPoint(0)
    end = line.GetEndPoint(1)
    span = end - start
    width = span.GetLength()

    bounding_box = crop_element.get_BoundingBox(None)
    min_z = bounding_box.Min.Z
    max_z = bounding_box.Max.Z

    direction = span.Normalize()
    up = DB.XYZ.BasisZ

    transform = DB.Transform.Identity
    transform.Origin = start + 0.5 * span
    transform.BasisX = direction
    transform.BasisY = up
    transform.BasisZ = direction.CrossProduct(up)

    section_box = DB.BoundingBoxXYZ()
    section_box.Transform = transform
    section_box.Min = DB.XYZ(-width, min_z - offset, -offset)
    section_box.Max = DB.XYZ(width, max_z + offset, offset)
    return section_box


def find_crop_box(doc, view):
    """Return the crop-box element of a view (Revit exposes no direct API for it).

    The crop box is toggled off/on and the newly appearing view-specific element
    is captured; the whole operation is rolled back afterwards.
    """
    crop_box_element = None
    group = DB.TransactionGroup(doc, 'Find Crop Box')
    group.Start()
    try:
        transaction = DB.Transaction(doc, 'Find Crop Box')
        transaction.Start()
        view.CropBoxVisible = False
        transaction.Commit()

        hidden_ids = DB.FilteredElementCollector(doc, view.Id).ToElementIds()

        transaction.Start()
        view.CropBoxVisible = True
        transaction.Commit()

        crop_box_element = DB.FilteredElementCollector(doc, view.Id) \
            .Excluding(hidden_ids) \
            .FirstElement()
    finally:
        group.RollBack()
    return crop_box_element


def get_bb_axis_in_view(element, view):
    bounding_box = element.get_BoundingBox(view)
    center = 0.5 * (bounding_box.Max + bounding_box.Min)
    return DB.Line.CreateBound(center, center + DB.XYZ.BasisZ)


def _curve_loop_from_corners(corners):
    return DB.CurveLoop.Create(List[DB.Curve](corners))


def _offset_outwards(curve_loop, offset, view_direction):
    offset_loop = DB.CurveLoop.CreateViaOffset(curve_loop, offset, view_direction)
    if offset_loop.GetExactLength() < curve_loop.GetExactLength():
        offset_loop = DB.CurveLoop.CreateViaOffset(curve_loop, offset, -view_direction)
    return offset_loop


def set_crop_to_bb(room, view, crop_offset, doc=None):
    """Crop an elevation/section view to the room's extent, plus the crop offset."""
    doc = doc or revit.doc
    view.CropBoxActive = False
    doc.Regenerate()

    bounding_box = room.get_BoundingBox(view)
    if bounding_box is None:
        return False

    max_x, max_y = bounding_box.Max.X, bounding_box.Max.Y
    min_x, min_y = bounding_box.Min.X, bounding_box.Min.Y
    min_z, max_z = bounding_box.Min.Z, bounding_box.Max.Z

    first_set = [
        DB.Line.CreateBound(DB.XYZ(max_x, max_y, min_z), DB.XYZ(max_x, max_y, max_z)),
        DB.Line.CreateBound(DB.XYZ(max_x, max_y, max_z), DB.XYZ(min_x, min_y, max_z)),
        DB.Line.CreateBound(DB.XYZ(min_x, min_y, max_z), DB.XYZ(min_x, min_y, min_z)),
        DB.Line.CreateBound(DB.XYZ(min_x, min_y, min_z), DB.XYZ(max_x, max_y, min_z)),
    ]
    second_set = [
        DB.Line.CreateBound(DB.XYZ(max_x, min_y, min_z), DB.XYZ(max_x, min_y, max_z)),
        DB.Line.CreateBound(DB.XYZ(max_x, min_y, max_z), DB.XYZ(min_x, max_y, max_z)),
        DB.Line.CreateBound(DB.XYZ(min_x, max_y, max_z), DB.XYZ(min_x, max_y, min_z)),
        DB.Line.CreateBound(DB.XYZ(min_x, max_y, min_z), DB.XYZ(max_x, min_y, min_z)),
    ]

    view.CropBoxActive = True
    crop_shape_manager = view.GetCropRegionShapeManager()
    view_direction = view.ViewDirection

    for corners in (first_set, second_set):
        try:
            crop_shape_manager.SetCropShape(
                _offset_outwards(_curve_loop_from_corners(corners),
                                 crop_offset, view_direction))
            return True
        except Exception:
            continue

    view.CropBoxActive = False
    return False


def _bb_corners(bounding_box, transform):
    """Section-box corners converted from world into view coordinates."""
    corners = [
        bounding_box.Min,
        DB.XYZ(bounding_box.Max.X, bounding_box.Min.Y, bounding_box.Min.Z),
        DB.XYZ(bounding_box.Min.X, bounding_box.Max.Y, bounding_box.Min.Z),
        DB.XYZ(bounding_box.Max.X, bounding_box.Max.Y, bounding_box.Min.Z),
        bounding_box.Max,
        DB.XYZ(bounding_box.Min.X, bounding_box.Max.Y, bounding_box.Max.Z),
        DB.XYZ(bounding_box.Max.X, bounding_box.Min.Y, bounding_box.Max.Z),
        DB.XYZ(bounding_box.Min.X, bounding_box.Min.Y, bounding_box.Max.Z),
    ]
    transformed = []
    for corner in corners:
        transformed.append(
            transform.Inverse.OfPoint(bounding_box.Transform.OfPoint(corner)))
    return transformed


def crop_axo(view3d):
    if not view3d.IsSectionBoxActive:
        return

    view3d.CropBoxActive = True
    crop_box = view3d.CropBox
    section_box = view3d.GetSectionBox()
    transform = crop_box.Transform
    corners = _bb_corners(section_box, transform)

    min_x = min(corners, key=lambda p: p.X).X
    min_y = min(corners, key=lambda p: p.Y).Y
    min_z = min(corners, key=lambda p: p.Z).Z
    max_x = max(corners, key=lambda p: p.X).X
    max_y = max(corners, key=lambda p: p.Y).Y
    max_z = max(corners, key=lambda p: p.Z).Z

    offset = 0.05 * (max_x - min_x)
    min_x, max_x = min_x - offset, max_x + offset
    offset = 0.05 * (max_y - min_y)
    min_y, max_y = min_y - offset, max_y + offset

    crop_box.Min = DB.XYZ(min_x, min_y, min_z)
    crop_box.Max = DB.XYZ(max_x, max_y, max_z)
    view3d.CropBox = crop_box


def create_room_axo_rotate(room, angle=None, view_scale=DEFAULT_VIEW_SCALE, doc=None):
    """Isometric 3D view cropped to the room, rotated with the room."""
    doc = doc or revit.doc
    if angle is None:
        angle = room_rotation_angle(room)

    three_d_type = get_view_family_types(DB.ViewFamily.ThreeDimensional, doc)[0]
    three_d = DB.View3D.CreateIsometric(doc, three_d_type.Id)
    three_d.Scale = view_scale

    rotation = DB.Transform.CreateRotationAtPoint(
        DB.XYZ.BasisZ, -angle, room.Location.Point)
    shell_bb = room.ClosedShell.GetTransformed(rotation).GetBoundingBox()

    section_box = DB.BoundingBoxXYZ()
    section_box.Transform = rotation.Inverse
    section_box.Min = shell_bb.Min
    section_box.Max = shell_bb.Max
    three_d.SetSectionBox(section_box)

    three_d.SetOrientation(DB.ViewOrientation3D(
        DB.XYZ(0, 0, 0), DB.XYZ(-1, 1, 2), DB.XYZ(-1, 1, -1)))
    three_d.CropBoxActive = True
    doc.Regenerate()
    crop_axo(three_d)
    return three_d


# ---------------------------------------------------------------------------
# sheet layout
# ---------------------------------------------------------------------------
GRID_COLUMNS = 4


def sheet_grid_positions(sheet, titleblock_offset, tb_orientation, count,
                         columns=GRID_COLUMNS):
    """Viewport centres for `count` views in a 4-column grid, top row first.

    The titleblock keeps its own band on the sheet, so that strip is taken off
    the usable width (vertical titleblock) or height (horizontal titleblock).
    """
    if count <= 0:
        return []

    x_min = sheet.Outline.Min.U
    y_min = sheet.Outline.Min.V
    width = sheet.Outline.Max.U - x_min
    height = sheet.Outline.Max.V - y_min

    if str(tb_orientation) == 'Vertical':
        width -= titleblock_offset
    else:
        height -= titleblock_offset

    columns = max(1, int(columns))
    rows = max(2, int(math.ceil(count / float(columns))))
    column_width = width / float(columns)
    row_height = height / float(rows)

    positions = []
    for index in range(count):
        row = index // columns
        column = index % columns
        positions.append(DB.XYZ(
            x_min + column_width * (column + 0.5),
            y_min + height - row_height * (row + 0.5),
            0))
    return positions


def realign_pos(doc, viewports, positions):
    """Move viewports onto their target points.

    A freshly placed viewport does not land on the requested point (the
    viewport label offsets it), so the delta is measured and applied.
    """
    for viewport, position in zip(viewports, positions):
        delta = position - viewport.GetBoxCenter()
        DB.ElementTransformUtils.MoveElement(doc, viewport.Id, delta)
