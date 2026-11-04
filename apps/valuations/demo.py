# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration valuations on the fictional Exampleton estate."""
from datetime import date
from decimal import Decimal as D

from apps.core.models import ModuleSettings
from apps.properties.models import Property

from . import programme
from .models import AssetClass, Classification, Valuation, ValuationComponent, ValuationSettings, Valuer
from .seed import FROM_PURPOSE

MARK = "DEMO"

# reference: (last valuation year, value, land, buildings, remaining life, method)
HISTORY = {
    "DM-E01": (2026, 6850000, 1900000, 4950000, 35, "investment"),
    "DM-S01": (2026, 3120000, 900000, 2220000, 30, "investment"),
    "DM-S02": (2022, 4100000, 650000, 3450000, 30, "drc"),
    "DM-S03": (2023, 1450000, 600000, 850000, 20, "drc"),
    "DM-S04": (2022, 980000, 520000, 460000, 15, "comparison"),
    "DM-S06": (2026, 1750000, 1750000, 0, None, "residual"),
    "DM-S07": (2026, 2380000, 410000, 1970000, 25, "investment"),
    "DM-S09": (2022, 640000, 180000, 460000, 25, "comparison"),
    "DM-S10": (2026, 210000, 210000, 0, None, "comparison"),
    "DM-S11": (2026, 165000, 40000, 125000, 20, "investment"),
}


def load(today=None):
    modules = ModuleSettings.load()
    if not modules.valuation_enabled:
        modules.valuation_enabled = True
        modules.save()
    if Valuer.objects.filter(rics_number__startswith=MARK).exists():
        return Valuation.objects.count()
    settings = ValuationSettings.load()
    internal = Valuer.objects.create(name="Sam Hughes", firm="Exampleton Council Estates", status="internal",
                                     rics_number=f"{MARK}-0001", registered_valuer=True,
                                     email="demo.head@example.org")
    external = Valuer.objects.create(name="Alex Fairweather", firm="Example Valuers LLP (fictional)",
                                     status="external", rics_number=f"{MARK}-0002", registered_valuer=True,
                                     email="valuations@example.org", first_instructed=date(2021, 11, 1),
                                     conflicts="None declared.")
    classes = {c.code: c for c in AssetClass.objects.all()}
    props = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-", parent__isnull=True)}
    for ref, prop in props.items():
        code = FROM_PURPOSE.get(prop.holding_purpose)
        if code in classes:
            Classification.objects.create(property=prop, asset_class=classes[code], effective_from=date(2021, 4, 1),
                                          reason="Opening classification (demonstration)")
    if "DM-S06" in props:  # declared surplus, then held for sale
        Classification.objects.filter(property=props["DM-S06"]).update(asset_class=classes["surplus"])
        Classification.objects.create(property=props["DM-S06"], asset_class=classes["held_for_sale"],
                                      effective_from=date(2025, 9, 1),
                                      reason="Cabinet approved disposal, September 2025 (fictional)")
    for ref, (year, value, land, buildings, life, method) in HISTORY.items():
        if ref not in props:
            continue
        cls = programme.current_class(props[ref], date(year, 3, 31))
        v = Valuation(property=props[ref], asset_class=cls.asset_class, basis=cls.asset_class.basis,
                      valuation_date=date(year, 3, 31), valuer=external if cls.asset_class.cycle_years == 1 else internal,
                      terms_agreed_on=date(year - 1, 11, 15), inspection_date=date(year - 1, 12, 10),
                      inspection="full" if year != 2026 or ref == "DM-S07" else "desktop",
                      report_date=date(year, 4, 20), method=method, value=D(value), land_value=D(land),
                      building_value=D(buildings), remaining_life=life, status="accepted",
                      accepted_on=date(year, 5, 10))
        if ref == "DM-S07":
            v.occupation_then = "let"  # fully let when valued; partly vacant now: an impairment prompt
        v.save()
        if ref == "DM-S02":
            for name, val, yrs in [("Structure and frame", 1900000, 60), ("Roof", 450000, 20),
                                   ("Mechanical and electrical services", 800000, 15), ("Fit-out", 300000, 12)]:
                ValuationComponent.objects.create(valuation=v, name=name, value=D(val), useful_life=yrs)
    # This year's programme, with two valuations back from the valuer
    year_end = settings.year_end(today)
    programme.start(year_end, valuer=external)
    for ref, value, land, buildings, life in [("DM-E01", 7100000, 1950000, 5150000, 34),
                                              ("DM-S02", 4380000, 700000, 3680000, 29)]:
        v = Valuation.objects.filter(property__reference=ref, valuation_date=year_end).first()
        if v:
            v.value, v.land_value, v.building_value, v.remaining_life = D(value), D(land), D(buildings), life
            v.terms_agreed_on, v.method, v.inspection = date(year_end.year - 1, 10, 20), \
                "investment" if ref == "DM-E01" else "drc", "full"
            v.inspection_date, v.status = date(year_end.year - 1, 11, 25), "received"
            v.save()
    return Valuation.objects.count()


def remove():
    from apps.cases.models import Case

    refs = Property.objects.filter(reference__startswith="DM-")
    cases = list(Valuation.objects.filter(property__in=refs).values_list("case_id", flat=True))
    Valuation.objects.filter(property__in=refs).delete()
    Case.objects.filter(pk__in=[c for c in cases if c]).delete()
    Case.objects.filter(case_type__code="valuation_programme", title__startswith="Valuation programme").delete()
    Classification.objects.filter(property__in=refs).delete()
    Valuer.objects.filter(rics_number__startswith=MARK).delete()
