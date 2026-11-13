# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration values for the details the Government Property Data Standard asks for: use from the list,
designations, acquisition, overall condition, vacancy, planned disposal, and running costs and rates.

Worked out from each demonstration property's own record so both fictional estates are covered. All invented.
"""
from datetime import date, timedelta
from decimal import Decimal

from .models import Property, PropertyCost, PropertyUse

# Words in the free-text use, and the entry in the list of uses they point to. First match wins.
USE_WORDS = [
    ("car park", "Car park"), ("librar", "Library"), ("leisure", "Leisure centre"), ("pitch", "Sports ground or pavilion"),
    ("pavilion", "Sports ground or pavilion"), ("community", "Community centre or hall"), ("allotment", "Allotments"),
    ("market", "Market"), ("caf", "Café or restaurant"), ("kiosk", "Café or restaurant"), ("mast", "Telecoms mast"),
    ("farm", "Farm or agricultural land"), ("grazing", "Farm or agricultural land"),
    ("agricultur", "Farm or agricultural land"), ("road", "Estate roads and common areas"),
    ("development", "Development land"), ("brownfield", "Development land"), ("cleared", "Development land"),
    ("depot", "Depot"), ("waste", "Depot"), ("warehouse", "Warehouse or storage"), ("workshop", "Workshop"),
    ("industrial", "Industrial unit"), ("business park", "Industrial unit"), ("office", "Office"),
    ("council", "Civic building"), ("civic", "Civic building"), ("shop", "Shop"), ("retail", "Shop"),
    ("precinct", "Shop"), ("confidential", "Other"),
]
HERITAGE = ("library", "market", "town hall", "civic", "old ")


def load(today=None):
    """Fill in the details on demonstration properties (references starting DM-). Safe to run again."""
    today = today or date.today()
    uses = {u.name: u for u in PropertyUse.objects.all()}
    year = today.year if today.month >= 4 else today.year - 1  # the financial year now running
    for n, p in enumerate(Property.objects.filter(reference__startswith="DM-").order_by("reference")):
        text = f"{p.use_description} {p.name}".lower()
        if p.use_type_id is None:
            p.use_type = next((uses[name] for word, name in USE_WORDS if word in text and name in uses), None)
        top = p.parent_id is None
        if top and not p.acquired_on:
            p.acquired_on = date(1974, 4, 1) if n % 3 else date(1998 + n % 20, 6 + n % 6, 1 + n % 27)
        if p.property_type in ("building", "site") and (p.built or p.building_description or top):
            heritage = any(word in text for word in HERITAGE)
            if not p.listed_building:
                p.listed_building = "2" if heritage and p.property_type == "building" else "no"
                p.conservation_area = "yes" if heritage else "no"
                p.scheduled_monument = p.sssi = "no"
                if p.listed_building == "2":
                    p.designation_notes = "List entry 1400000 (fictional). The listing covers the frontage."
            if p.property_type == "building" and not p.condition_grade:
                p.condition_grade = "BBCBAC"[n % 6]
                p.condition_surveyed_on = today - timedelta(days=200 + 150 * (n % 9))
        if p.occupation == "vacant" and not p.children.exists() and not p.vacant_since:
            p.vacant_since = today - timedelta(days=45 + 60 * (n % 6))
            p.vacancy_status = ("available", "under_offer", "available", "withdrawn")[n % 4]
            if p.vacancy_status != "withdrawn":
                p.available_from = p.vacant_since + timedelta(days=30)
        if p.holding_purpose in ("surplus", "held_for_sale") and not p.disposed_on and not p.disposal_reason:
            p.disposal_reason = "Declared surplus after the service's property review (fictional)."
            p.disposal_method = "informal_tender" if p.property_type == "land" else "private_treaty"
            p.disposal_expected_on = today + timedelta(days=240)
            base = (p.site_area_ha or Decimal("0.5")) * Decimal("900000")
            p.disposal_expected_value = base.quantize(Decimal("1000"))
        p.save()
        if p.occupation == "council" and p.gia_sqm and not p.costs.exists():
            for back, factor in ((1, Decimal("0.96")), (0, Decimal("1"))):
                PropertyCost.objects.create(
                    property=p, year_starting=year - back,
                    running_cost=(p.gia_sqm * Decimal("62") * factor).quantize(Decimal("100")),
                    rates=(p.gia_sqm * Decimal("38") * factor).quantize(Decimal("100")),
                    notes="Estimate for the year so far" if back == 0 else "From the finance system (fictional)")
