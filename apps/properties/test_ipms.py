# SPDX-License-Identifier: AGPL-3.0-or-later
"""Floor areas to IPMS: All Buildings, held beside the Code of Measuring Practice figures."""
import importlib
from datetime import date
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.urls import reverse

from apps.core.models import ModuleSettings
from apps.core.roles import ADMINISTRATORS, SURVEYORS
from apps.properties import importer, standard
from apps.properties.models import Property
from apps.properties.report import build as build_report

PASSWORD = "a-long-test-password"


@pytest.fixture
def hall(db):
    return Property.objects.create(
        reference="H-1", name="Civic hall", property_type="building", gia_sqm=Decimal("1000"),
        nia_sqm=Decimal("800"), area_standard="comp6", area_source="drawings", ipms2_sqm=Decimal("1012"),
        ipms3_sqm=Decimal("790"), ipms3_kind="3.2", ipms1_sqm=Decimal("1100"), ipms_source="survey",
        ipms_measured_on=date(2026, 6, 1), ipms_measured_by="Example Surveys", ipms_method="Laser and CAD",
        ipms_checked="yes", ipms_checked_how="two floors check-measured", ipms_notes="Roof terrace 40 m² stated separately")


def _basis(value):
    ms = ModuleSettings.load()
    ms.area_basis = value
    ms.save()


def test_headline_basis_and_fallback(hall):
    assert hall.floor_area("gross") == (Decimal("1000"), "GIA")
    assert hall.floor_area("net") == (Decimal("800"), "NIA")
    _basis("ipms")
    hall = Property.objects.get(pk=hall.pk)  # the basis is read once per record
    assert hall.floor_area("gross") == (Decimal("1012"), "IPMS 2")
    assert hall.floor_area("net") == (Decimal("790"), "IPMS 3.2")
    assert hall.floor_area("external") == (Decimal("1100"), "IPMS 1")
    assert [label for label, _v in hall.area_lines()][:3] == ["IPMS 1", "IPMS 2", "IPMS 3.2"]
    # only one set held: that one is used, whatever the setting
    only_comp = Property.objects.create(reference="O-1", name="Old", property_type="building", gia_sqm=Decimal("50"))
    assert only_comp.floor_area("gross") == (Decimal("50"), "GIA")
    assert only_comp.floor_area("external") == (None, "")


def test_basis_text(hall):
    assert hall.comp_basis_text().startswith("RICS Code of Measuring Practice, 6th edition; taken from drawings")
    text = hall.ipms_basis_text()
    assert text.startswith("IPMS: All Buildings; measured survey; Example Surveys; Laser and CAD")
    assert "checked on site (two floors check-measured)" in text and "1 June 2026" in text


def test_property_page_and_report(client, hall, make_user):
    make_user("boss", ADMINISTRATORS)
    client.login(username="boss", password=PASSWORD)
    page = client.get(hall.get_absolute_url()).content.decode()
    assert "GIA 1,000 m²" in page and "IPMS 2 1,012 m²" in page and "IPMS 3.2 790 m²" in page
    assert "IPMS: All Buildings; measured survey" in page and "Roof terrace" in page
    text = build_report(hall)
    assert "| IPMS 2 | 1,012 m² |" in text and "Gross internal area (GIA)" in text
    assert text.count("Basis of measurement") == 2


def test_space_and_data_standard_follow_the_basis(hall):
    from apps.space.costs import total_area

    hall.nia_sqm = None
    hall.save()
    assert total_area(Property.objects.get(pk=hall.pk), date.today()) == Decimal("790")  # IPMS 3 before GIA
    assert standard._floor_area(Property.objects.get(pk=hall.pk)) == (
        Decimal("1000"), "GIA (RICS Code of Measuring Practice, 6th edition)")
    _basis("ipms")
    assert standard._floor_area(Property.objects.get(pk=hall.pk)) == (Decimal("1012"), "IPMS 2 (IPMS: All Buildings)")


def test_importer_columns(db):
    rows = [(2, {"reference": "I-1", "name": "Imported", "property_type": "Building", "ipms2_sqm": "500",
                 "ipms3_sqm": "420", "ipms3_kind": "IPMS 3.2", "ipms_checked": "Yes",
                 "ipms_measured_on": "01/05/2026", "ipms_source": "Measured survey"}),
            (3, {"reference": "I-2", "name": "Wrong box", "property_type": "Building", "gia_sqm": "100",
                 "area_standard": "IPMS: All Buildings"})]
    result, prepared = importer.validate(rows)
    first, second = result.rows
    assert not first.errors
    assert any("IPMS columns" in e for e in second.errors)
    obj = prepared[0][0]
    assert obj.ipms2_sqm == Decimal("500") and obj.ipms3_kind == "3.2" and obj.ipms_checked == "yes"


def test_old_ipms_figures_are_moved(db):
    migration = importlib.import_module("apps.properties.migrations.0012_ipms_areas")
    p = Property.objects.create(reference="M-1", name="Measured", property_type="building", gia_sqm=Decimal("900"),
                                nia_sqm=Decimal("700"), gea_sqm=Decimal("980"), area_source="survey",
                                areas_measured_on=date(2025, 3, 1))
    Property.objects.filter(pk=p.pk).update(area_standard="ipms")
    keep = Property.objects.create(reference="M-2", name="Code", property_type="building", gia_sqm=Decimal("10"),
                                   area_standard="comp6")
    migration.move_ipms_figures(django_apps, None)
    p.refresh_from_db()
    keep.refresh_from_db()
    assert (p.ipms1_sqm, p.ipms2_sqm, p.ipms3_sqm) == (Decimal("980"), Decimal("900"), Decimal("700"))
    assert p.gia_sqm is None and p.area_standard == "" and p.ipms_source == "survey"
    assert p.ipms_measured_on == date(2025, 3, 1) and "Moved from" in p.ipms_notes
    assert keep.gia_sqm == Decimal("10") and keep.ipms2_sqm is None


def test_check_measure_offers_the_councils_basis(hall, make_user):
    from apps.cases import visit

    assert "gia_sqm" in visit.update_fields("floor_areas", hall)
    _basis("ipms")
    hall = Property.objects.get(pk=hall.pk)
    fields = visit.update_fields("floor_areas", hall)
    assert "ipms2_sqm" in fields and "gia_sqm" not in fields
    assert make_user("sue", SURVEYORS)


def test_module_setting_in_manage_data(client, make_user, db):
    make_user("boss", ADMINISTRATORS)
    client.login(username="boss", password=PASSWORD)
    ms = ModuleSettings.load()
    page = client.get(reverse("admin:core_modulesettings_change", args=[ms.pk])).content.decode()
    assert "Floor areas: show first" in page
