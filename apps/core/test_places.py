# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date

import pytest

from apps.core.models import ModuleSettings
from apps.properties.models import Property


@pytest.fixture
def estate(db, make_user):
    settings = ModuleSettings.load()
    settings.maintenance_enabled = settings.valuation_enabled = True
    settings.save()
    one, two = make_user("one", "Surveyors"), make_user("two", "Surveyors")
    a = Property.objects.create(reference="A", name="Block A", property_type="building", managing_surveyor=one)
    a1 = Property.objects.create(reference="A1", name="Unit A1", property_type="unit", parent=a, managing_surveyor=one)
    b = Property.objects.create(reference="B", name="Block B", property_type="building", managing_surveyor=two)
    return {"one": one, "two": two, "a": a, "a1": a1, "b": b}


def test_components_planned_and_compliance_filter_by_building_and_surveyor(client, estate):
    from apps.compliance import workflow as compliance
    from apps.compliance.models import ComplianceType
    from apps.maintenance.models import Component, PlannedTask

    Component.objects.create(property=estate["a1"], name="Boiler in A1", category="mechanical")
    Component.objects.create(property=estate["b"], name="Roof of B", category="roof")
    PlannedTask.objects.create(property=estate["a1"], title="Gas check A1", frequency_months=12, next_due=date.today())
    PlannedTask.objects.create(property=estate["b"], title="Lift check B", frequency_months=6, next_due=date.today())
    gas = ComplianceType.objects.get(code="gas")
    compliance.add_requirements(estate["a1"], [gas])
    compliance.add_requirements(estate["b"], [gas])
    client.force_login(estate["one"])
    a, two = estate["a"].pk, estate["two"].pk
    page = client.get(f"/maintenance/components/?building={a}").content.decode()
    assert "Boiler in A1" in page and "Roof of B" not in page  # parts of the building are included
    page = client.get(f"/maintenance/components/?surveyor={two}").content.decode()
    assert "Roof of B" in page and "Boiler in A1" not in page
    page = client.get("/maintenance/planned/?surveyor=me").content.decode()
    assert "Gas check A1" in page and "Lift check B" not in page
    page = client.get(f"/compliance/?show=all&building={estate['b'].pk}").content.decode()
    assert ">B</a>" in page and ">A1</a>" not in page


def test_other_lists_accept_the_filters(client, estate):
    client.force_login(estate["one"])
    a = estate["a"].pk
    for url in ("/maintenance/jobs/", "/maintenance/contracts/", "/maintenance/forecast/", "/cases/", "/leases/events/",
                "/leases/", "/valuations/"):
        for query in (f"?building={a}", "?surveyor=me", "?surveyor=none"):
            assert client.get(url + query).status_code == 200, url + query
