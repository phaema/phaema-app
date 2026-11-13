# SPDX-License-Identifier: AGPL-3.0-or-later
"""The starting list of property uses, each matched to a term in the Government Property Data Standard's usage list.

Each council edits the list under Manage data, Property uses. The second value is the standard's term, used by the
standard's export; blank where nothing in the standard fits.
"""
import re

STARTING_USES = [
    ("Office", "Office"),
    ("Civic building", "Civic Building"),
    ("Shop", "Retail"),
    ("Café or restaurant", "Café"),
    ("Market", "Retail"),
    ("Industrial unit", "Industrial"),
    ("Workshop", "Workshop"),
    ("Warehouse or storage", "Warehouse"),
    ("Depot", "Depot"),
    ("Car park", "Car park"),
    ("Library", "Public Library"),
    ("Museum or gallery", "Museum"),
    ("Theatre or arts venue", "Theatre"),
    ("Leisure centre", "Leisure Centre"),
    ("Sports ground or pavilion", "Leisure/Sports Facility"),
    ("Community centre or hall", "Community Buildings"),
    ("Children's centre", "Children's Centre"),
    ("Youth centre", "Youth Facilities"),
    ("Day centre", "Day Centre"),
    ("School", "School"),
    ("Residential", "Residential"),
    ("Sheltered housing", "Sheltered Housing"),
    ("Hostel", "Hostel"),
    ("Travellers site", "Travellers Site"),
    ("Public toilets", "Public Toilets"),
    ("Park or open space", "Public open space"),
    ("Allotments", "Other Land"),
    ("Cemetery or crematorium", "Crematorium/Cemetery"),
    ("Farm or agricultural land", "Agricultural"),
    ("Woodland", "Woodland"),
    ("Development land", "Development land"),
    ("Vacant land", "Land"),
    ("Telecoms mast", "Radio Site"),
    ("Substation or utility", "Sub-station"),
    ("Heritage asset or monument", "Heritage Asset"),
    ("Waste site", "Waste disposal"),
    ("Estate roads and common areas", "Other Land"),
    ("Mixed use", "Various"),
    ("Other", ""),
]


def year_from(text):
    """The first four-digit year in a free-text 'built' value: 1987 from "c. 1987, extended 2004", 1930 from "1930s"."""
    match = re.search(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", text or "")
    return int(match.group(1)) if match else None
