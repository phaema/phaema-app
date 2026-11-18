# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupation and its costs on the property page, in the property report and on the site visit sheet."""
from django.urls import reverse

from apps.core.models import AccessArea, ModuleSettings
from apps.properties import report
from apps.properties.models import Property
from apps.space import overview

from .test_costs import PASSWORD, setup  # noqa: F401  (the fixture)


def _surveyor(make_user, *areas):
    sue = make_user("sue", "Surveyors")
    sue.access_areas.set(AccessArea.objects.filter(code__in=areas))
    return sue


def test_report_shows_occupation_to_estates_and_costs_only_with_costing(make_user, setup):  # noqa: F811
    b = setup["building"]
    sue = _surveyor(make_user, "estates")
    text = report.build(b, user=sue)
    assert "# 8. Occupation" in text or ". Occupation\n" in text
    assert "| Housing |" in text and "Checked on site" in text and "NHS clinic (outside the council)" in text
    assert "Occupation costs" not in text
    sue.access_areas.add(AccessArea.objects.get(code="finance"))
    text = report.build(b, user=type(sue).objects.get(pk=sue.pk))  # a fresh copy, as on the next request
    assert ". Occupation costs\n" in text and "Notional £" in text and "corporate landlord" in text


def test_report_leaves_occupation_out_when_space_is_off(make_user, setup):  # noqa: F811
    settings = ModuleSettings.load()
    settings.space_enabled = False
    settings.save()
    text = report.build(setup["building"], user=_surveyor(make_user, "estates", "finance"))
    assert "Occupation\n" not in text and "Occupation costs" not in text
    assert overview.for_property(setup["building"], None) is None


def test_estate_report_covers_buildings_within(make_user, setup):  # noqa: F811
    estate = Property.objects.create(reference="EST", name="Civic estate", property_type="estate")
    b = setup["building"]
    b.parent = estate
    b.save()
    text = report.build(estate, user=_surveyor(make_user, "estates"))
    assert "## Building: CC1 Civic Centre" in text and "| Housing |" in text


def test_report_without_records_says_so(make_user, setup):  # noqa: F811
    empty = Property.objects.create(reference="EMPTY", name="Empty", property_type="building")
    text = report.build(empty, user=_surveyor(make_user, "estates", "finance"))
    assert "No occupiers are recorded" in text and "No occupation costs are recorded" in text


def test_property_page_summary(client, make_user, setup):  # noqa: F811
    b = setup["building"]
    sue = _surveyor(make_user, "estates")
    client.login(username="sue", password=PASSWORD)
    page = client.get(b.get_absolute_url()).content.decode()
    assert 'id="occupation"' in page and "Housing" in page and "NHS clinic" in page
    assert reverse("space:building", args=[b.pk]) in page and "Cost " not in page
    sue.access_areas.add(AccessArea.objects.get(code="finance"))
    page = client.get(b.get_absolute_url()).content.decode()
    assert "Cost " in page and "corporate landlord" in page


def test_property_page_hides_summary_when_space_is_off(client, make_user, setup):  # noqa: F811
    settings = ModuleSettings.load()
    settings.space_enabled = False
    settings.save()
    _surveyor(make_user, "estates")
    client.login(username="sue", password=PASSWORD)
    assert 'id="occupation"' not in client.get(setup["building"].get_absolute_url()).content.decode()


def test_site_visit_sheet_can_include_occupation(make_user, setup):  # noqa: F811
    assert "occupation" in report.ALL_PARTS and "occupation_costs" in report.ALL_PARTS
    sections = dict(report.sections(setup["building"], wanted=["occupation"],
                                    gathered=report.Gathered(setup["building"],
                                                             user=_surveyor(make_user, "estates"))))
    assert "Occupation" in sections
