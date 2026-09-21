# -*- coding: utf-8 -*-
"""List all families and their sizes."""
import os
import re
import math
import tempfile
from collections import defaultdict
from pyrevit import revit, forms, script, DB, HOST_APP

output = script.get_output()
logger = script.get_logger()

FIELDS = ["Size", "Name", "Category", "Creator", "Count"]
# temporary path for saving families
temp_dir = os.path.join(tempfile.gettempdir(), "pyRevit_ListFamilySizes")
if not os.path.exists(temp_dir):
    os.mkdir(temp_dir)
save_as_options = DB.SaveAsOptions()
save_as_options.OverwriteExistingFile = True

# characters that are illegal in a windows file name, plus the reserved
#  device names, which can not be used as a file name either
ILLEGAL_FILE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_FILE_NAME_PARTS = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL'] +
    ['COM{}'.format(i) for i in range(1, 10)] +
    ['LPT{}'.format(i) for i in range(1, 10)]
)
MAX_FILE_NAME_LENGTH = 120


def make_temp_file_path(name):
    """Build a saveable temporary .rfa path out of a revit family name.

    A revit family name is not guaranteed to be a valid windows file name. A
    ':' for example turns the rest of the path into an NTFS alternate data
    stream reference, which Revit reports as an unreadable/unsaveable file,
    and without the '.rfa' extension Revit saves to a different file than the
    one this script then measures and deletes.
    """
    # the temp folder can be cleaned up by the OS or by a security agent
    #  while the script is running, so make sure it is still there
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_name = ILLEGAL_FILE_NAME_CHARS.sub('_', name or '')
    # windows silently strips trailing dots and spaces from file names
    file_name = file_name.strip().rstrip('.').strip() or 'Unnamed'
    if file_name.split('.')[0].upper() in RESERVED_FILE_NAME_PARTS:
        file_name = '_' + file_name
    if len(file_name) > MAX_FILE_NAME_LENGTH:
        file_name = file_name[:MAX_FILE_NAME_LENGTH].rstrip('. ').strip()

    file_path = os.path.join(temp_dir, file_name + '.rfa')
    # a leftover file from a cancelled run may still be locked by Revit
    index = 1
    while os.path.exists(file_path) and index <= 20:
        try:
            os.remove(file_path)
            break
        except Exception:
            file_path = os.path.join(
                temp_dir, '{}_{}.rfa'.format(file_name, index))
            index += 1
    return file_path


def convert_size(size_bytes):
    if not size_bytes:
        return "N/A"
    size_unit = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    size = round(size_bytes / p, 2)
    return "{}{}".format(size, size_unit[i])


def print_totals(families):
    total_size = sum([fam_item.get("Size") or 0 for fam_item in families])
    output.print_md("### %d families, found total size: %s\n\n" % (
        len(families), convert_size(total_size)))


def print_sorted(families, group_by):
    # group by provided field, use the next field in the list to sort by
    fields_rest = list(FIELDS)
    fields_rest.pop(FIELDS.index(group_by))
    sort_by = fields_rest[0]
    fields_sorted = [group_by] + fields_rest

    if group_by not in ["Creator", "Category"]:  # do not group by name, size, and count
        output.print_md("**Sort by: {}**".format(group_by))
        # Handle numeric sorting for Size and Count fields
        if group_by in ["Size", "Count"]:
            families_grouped = {
                "": sorted(
                    families,
                    key=lambda fam_item: fam_item.get(group_by) or 0,
                    reverse=True
                )
            }
        else:
            families_grouped = {
                "": sorted(
                    families,
                    key=lambda fam_item: fam_item.get(group_by),
                    reverse=False
                )
            }
    else:
        output.print_md("## Group by: {}".format(group_by))
        output.print_md("## Sort by: {}".format(sort_by))
        # convert to grouped dict
        families_grouped = {}
        # Handle numeric sorting for Size and Count fields
        if sort_by in ["Size", "Count"]:
            sorted_families = sorted(
                families,
                key=lambda fam_item: fam_item.get(sort_by) or 0,
                reverse=True
            )
        else:
            sorted_families = sorted(
                families,
                key=lambda fam_item: fam_item.get(sort_by),
                reverse=False
            )

        for fam_item in sorted_families:
            group_by_value = fam_item[group_by]
            if group_by_value not in families_grouped:
                families_grouped[group_by_value] = []
            families_grouped[group_by_value].append(fam_item)

    for group_value in sorted(families_grouped.keys()):
        if group_by in ["Creator", "Category"]:
            output.print_md("---")
            output.print_md("## {}: {}".format(group_by, group_value))

        # Prepare table data
        table_data = []
        for fam_item in families_grouped[group_value]:
            row = []
            for field in fields_sorted:
                value = fam_item.get(field)
                if value is None:
                    row.append("N/A")
                elif field == "Size":
                    row.append(convert_size(value))
                else:
                    row.append(str(value))
            table_data.append(row)

        # Print table using output.print_table()
        output.print_table(
            table_data,
            columns=fields_sorted
        )

        print_totals(families_grouped[group_value])


# main logic
# ask use to choose sort option
sort_by = forms.CommandSwitchWindow.show(
    FIELDS,
    message="Sorting options:",
)
if not sort_by:
    script.exit()

all_fams = DB.FilteredElementCollector(revit.doc)\
             .OfClass(DB.Family)\
             .ToElements()

all_family_items = []
opened_families = [od.Title for od in HOST_APP.uiapp.Application.Documents
                   if od.IsFamilyDocument]

# Get all family instances to count them
all_family_instances = DB.FilteredElementCollector(revit.doc)\
                        .OfClass(DB.FamilyInstance)\
                        .ToElements()

# Create a dictionary to count instances per family
family_instance_counts = defaultdict(int)
for instance in all_family_instances:
    try:
        if hasattr(instance, 'Symbol') and instance.Symbol:
            family_name = instance.Symbol.Family.Name
            family_instance_counts[family_name] += 1
    except Exception:
        continue

# families that could not be measured because they could not be saved
save_failures = []

with forms.ProgressBar(title="List family sizes", cancellable=True) as pb:
    i = 0

    for fam in all_fams:
        with revit.ErrorSwallower() as swallower:
            if fam.IsEditable:
                try:
                    fam_doc = revit.doc.EditFamily(fam)
                except Exception as ex:
                    logger.warning(
                        "Skipping family '%s': could not open for edit: %s",
                        fam.Name, ex
                    )
                    continue
                fam_path = fam_doc.PathName
                temp_path = None
                # if the family path does not exists, save it temporary
                #  only if the wasn't opened when the script was started
                if fam_doc.Title not in opened_families and (
                        not fam_path or not os.path.exists(fam_path)):
                    # save with temporary path, to know family size
                    try:
                        temp_path = make_temp_file_path(
                            fam.Name or fam_doc.Title)
                        fam_doc.SaveAs(temp_path, save_as_options)
                        # let revit tell us where it actually saved to
                        fam_path = fam_doc.PathName or temp_path
                    except Exception as ex:
                        logger.warning(
                            "No size for family '%s': could not save a "
                            "temporary copy to '%s': %s",
                            fam.Name, temp_path, ex
                        )
                        temp_path = None
                        fam_path = None
                        save_failures.append(fam.Name)

                fam_size = 0
                fam_category = fam.FamilyCategory.Name if fam.FamilyCategory \
                    else "N/A"
                fam_creator = \
                    DB.WorksharingUtils.GetWorksharingTooltipInfo(revit.doc,
                                                                  fam.Id).Creator
                if fam_path and os.path.exists(fam_path):
                    fam_size = os.path.getsize(fam_path)

                # Get instance count for this family
                fam_count = family_instance_counts.get(fam.Name, 0)

                all_family_items.append({"Size": fam_size,
                                         "Creator": fam_creator,
                                         "Category": fam_category,
                                         "Name": fam.Name,
                                         "Count": fam_count})
                # if the family wasn't opened before, close it
                if fam_doc.Title not in opened_families:
                    try:
                        fam_doc.Close(False)
                    except Exception as ex:
                        logger.warning(
                            "Could not close family '%s': %s", fam.Name, ex)
                    # remove temporary family
                    if temp_path:
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception as ex:
                            logger.warning(
                                "Could not remove the temporary family '%s': "
                                "%s", temp_path, ex)
        if pb.cancelled:
            break
        else:
            pb.update_progress(i, len(all_fams))
        i += 1


# print results
if save_failures:
    output.print_md(
        "### %d families could not be saved to a temporary file and are "
        "listed as N/A (see the pyRevit log for details)\n\n"
        % len(save_failures))
print_sorted(all_family_items, sort_by)
