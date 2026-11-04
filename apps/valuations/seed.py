# SPDX-License-Identifier: AGPL-3.0-or-later
"""Starting asset classes, following the classes in the CIPFA Code of Practice on Local Authority Accounting.
They are defaults: finance sets the bases and cycles it uses, under Manage data."""

# code, name, basis, alternative basis, revalue every (years), index, depreciated, notes
CLASSES = [
    ("operational", "Other land and buildings (operational)", "euv", "drc", 5, "BCIS for DRC valuations", True,
     "Existing use value; depreciated replacement cost for specialised buildings with no market evidence."),
    ("investment", "Investment property", "fv", "", 1, "", False,
     "Fair value at each balance sheet date; not depreciated."),
    ("surplus", "Surplus assets", "fv", "", 5, "", True, "Fair value (highest and best use)."),
    ("held_for_sale", "Assets held for sale", "fv_sale", "", 1, "", False,
     "Lower of carrying amount and fair value less costs to sell; not depreciated."),
    ("heritage", "Heritage assets", "other", "", None, "", False,
     "Valuation where practicable, otherwise cost. Set the approach finance uses."),
    ("community", "Community assets", "historic", "", None, "", False, "Historic cost; not revalued."),
    ("under_construction", "Assets under construction", "historic", "", None, "", False,
     "Historic cost until complete, then reclassified."),
]

# Holding purpose in the property register -> suggested class
FROM_PURPOSE = {"operational": "operational", "investment": "investment", "community": "community",
                "surplus": "surplus", "held_for_sale": "held_for_sale"}


def ensure_classes():
    from .models import AssetClass

    for i, (code, name, basis, alt, cycle, index, depreciated, notes) in enumerate(CLASSES):
        AssetClass.objects.get_or_create(code=code, defaults={
            "name": name, "basis": basis, "alternative_basis": alt, "cycle_years": cycle, "index": index,
            "depreciated": depreciated, "notes": notes, "order": i * 10})
