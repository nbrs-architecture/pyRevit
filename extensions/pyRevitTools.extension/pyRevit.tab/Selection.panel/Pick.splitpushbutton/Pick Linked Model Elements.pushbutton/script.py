"""Picks elements inside linked models (model elements within Revit links).

Elements are always selected as a WHOLE - never by a clicked face or edge.
"""

from pyrevit.framework import List
from pyrevit import revit, DB, UI
from pyrevit.forms import alert


def _resolve_linked(reference, doc):
    """Return (link_instance, linked_element) for a linked-model pick reference."""
    if reference is None or reference.LinkedElementId == DB.ElementId.InvalidElementId:
        return None, None

    link_instance = doc.GetElement(reference.ElementId)
    if not isinstance(link_instance, DB.RevitLinkInstance):
        return None, None

    link_doc = link_instance.GetLinkDocument()
    if not link_doc:
        return None, None

    return link_instance, link_doc.GetElement(reference.LinkedElementId)


class LinkedModelElementFilter(UI.Selection.ISelectionFilter):
    """Allows picking only model elements that live inside a Revit link."""

    def __init__(self, doc):
        self._doc = doc

    # standard API override function
    # governs host-document elements; for linked picks the element passed
    # here is the parent RevitLinkInstance itself.
    def AllowElement(self, element):
        return isinstance(element, DB.RevitLinkInstance)

    # standard API override function
    # governs the actual elements inside the linked model
    def AllowReference(self, reference, point):
        _, linked_element = _resolve_linked(reference, self._doc)
        if not linked_element:
            return False
        # only allow model (non view-specific) elements inside the link
        return not linked_element.ViewSpecific


def _whole_element_reference(reference, doc):
    """Build a host-document reference that selects the picked linked element
    as a WHOLE, so it is never selected by a clicked face or edge.

    The reference returned by the pick may point at the geometry the user
    clicked (a face/edge). Rebuilding it from the linked element itself and
    converting it with CreateLinkReference selects the entire element.
    """
    link_instance, linked_element = _resolve_linked(reference, doc)
    if not link_instance or not linked_element:
        return None
    try:
        linked_ref = DB.Reference(linked_element)
        return linked_ref.CreateLinkReference(link_instance)
    except Exception:
        return None


try:
    doc = revit.doc
    picked_refs = revit.uidoc.Selection.PickObjects(
        UI.Selection.ObjectType.LinkedElement,
        LinkedModelElementFilter(doc),
        "Pick elements inside linked models. Press Esc to finish.",
    )

    if picked_refs:
        sel = revit.uidoc.Selection
        if hasattr(sel, "SetReferences"):  # Revit 2023+
            # select each picked element as a whole, never by a face or edge
            whole_refs = []
            unresolved = 0
            for picked_ref in picked_refs:
                whole_ref = _whole_element_reference(picked_ref, doc)
                if whole_ref:
                    whole_refs.append(whole_ref)
                else:
                    unresolved += 1

            if whole_refs:
                sel.SetReferences(List[DB.Reference](whole_refs))
                revit.uidoc.RefreshActiveView()

            if unresolved:
                alert(
                    "Could not select {0} of {1} picked element(s) as a "
                    "whole element.".format(unresolved, len(picked_refs))
                )
        else:  # Revit 2022 and older cannot select elements inside links
            alert(
                "Picked {0} linked element(s) but this Revit version cannot "
                "select elements inside linked models. "
                "Revit 2023 or newer is required.".format(len(picked_refs))
            )
except Exception:
    pass
