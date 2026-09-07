"""Picks elements inside linked models (model elements within Revit links)."""

from pyrevit.framework import List
from pyrevit import revit, DB, UI
from pyrevit.forms import alert


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
        # only references to an element inside a linked model are allowed
        if reference.LinkedElementId == DB.ElementId.InvalidElementId:
            return False

        # get the host link instance this reference belongs to
        link_instance = self._doc.GetElement(reference.ElementId)
        if not isinstance(link_instance, DB.RevitLinkInstance):
            return False

        # inspect the element inside the linked document
        link_doc = link_instance.GetLinkDocument()
        if not link_doc:
            return False

        linked_element = link_doc.GetElement(reference.LinkedElementId)
        if not linked_element:
            return False

        # only allow model (non view-specific) elements inside the link
        return not linked_element.ViewSpecific


try:
    picked_refs = revit.uidoc.Selection.PickObjects(
        UI.Selection.ObjectType.LinkedElement,
        LinkedModelElementFilter(revit.doc),
        "Pick elements inside linked models. Press Esc to finish.",
    )

    if picked_refs:
        sel = revit.uidoc.Selection
        if hasattr(sel, "SetReferences"):  # Revit 2023+
            sel.SetReferences(List[DB.Reference](list(picked_refs)))
            revit.uidoc.RefreshActiveView()
        else:  # Revit 2022 and older cannot select elements inside links
            alert(
                "Picked {0} linked element(s) but this Revit version cannot "
                "select elements inside linked models. "
                "Revit 2023 or newer is required.".format(len(picked_refs))
            )
except Exception:
    pass
