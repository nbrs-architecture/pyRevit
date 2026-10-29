#pylint: disable=import-error,invalid-name
from pyrevit import script, framework
from pyrevit import revit, DB
from Autodesk.Revit import Exceptions as RevitExceptions


selection = revit.get_selection()
output = script.get_output()


if not selection.is_empty:
    target = selection.first
    linked_elements_list = []
    if target is None:
        print("The selected element is not part of the active document.")
    else:
        print("Searching for all objects tied to ELEMENT ID: {0}..."
              .format(target.Id))
        try:
            # Revit 2026 refuses pinned elements in the single-id Delete
            # overload; the id set overload keeps deleting them silently.
            with revit.DryTransaction("Search for linked elements"):
                linked_elements_list = revit.doc.Delete(
                    framework.List[DB.ElementId]([target.Id])
                )
        except RevitExceptions.ArgumentException as delete_err:
            print("Revit cannot delete this element: {}"
                  .format(" ".join(delete_err.Message.split())))
            print("Referenced elements can only be listed for elements "
                  "Revit is able to delete.")

    for elId in linked_elements_list:
        el = revit.doc.GetElement(elId)
        if el and elId in selection.element_ids:
            elid_link = output.linkify(elId)
            print("ID: {}\t\tTYPE: {} ( selected object )"
                  .format(elid_link, el.GetType().Name))
        elif el:
            elid_link = output.linkify(elId)
            if isinstance(el, DB.FamilyInstance):
                family_name = revit.query.get_family_name(el)
                symbol_name = revit.query.get_symbol_name(el)
                print("ID: {}\t\tTYPE: {} ({}) --> {}:{}"
                      .format(elid_link,
                              el.GetType().Name,
                              el.Category.Name,
                              family_name,
                              symbol_name))
            else:
                print("ID: {}\t\tTYPE: {}"
                      .format(elid_link, el.GetType().Name))
