# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cases.models import Case
from apps.core.models import ModuleSettings
from apps.properties.models import Property
from apps.valuations import programme
from apps.valuations.models import AssetClass, Classification, Valuation, ValuationSettings, Valuer

YEAR_END = date(2027, 3, 31)


@pytest.fixture
def setup(db, make_user):
    settings = ModuleSettings.load()
    settings.valuation_enabled = True
    settings.save()
    surveyor = make_user("surv", "Surveyors")
    hall = Property.objects.create(reference="H1", name="Town Hall", property_type="building",
                                   holding_purpose="operational", occupation="council", managing_surveyor=surveyor)
    shops = Property.objects.create(reference="S1", name="Shops", property_type="building",
                                    holding_purpose="investment", occupation="let", managing_surveyor=surveyor)
    valuer = Valuer.objects.create(name="A Valuer", firm="Valuers LLP", first_instructed=date(2020, 1, 1))
    return {"surveyor": surveyor, "hall": hall, "shops": shops, "valuer": valuer,
            "admin": make_user("admin", "Administrators")}


def _accepted(prop, cls_code, when, value):
    cls = AssetClass.objects.get(code=cls_code)
    return Valuation.objects.create(property=prop, asset_class=cls, valuation_date=when, value=Decimal(value),
                                    status="accepted")


def test_classify_and_programme(client, setup):
    assert AssetClass.objects.get(code="investment").cycle_years == 1
    assert ValuationSettings.load().year_end(date(2026, 11, 4)) == YEAR_END
    client.force_login(setup["admin"])
    client.post("/valuations/", {"action": "classify", "from": "2021-04-01"})
    assert Classification.objects.count() == 2
    _accepted(setup["hall"], "operational", date(2023, 3, 31), 4000000)
    _accepted(setup["shops"], "investment", date(2026, 3, 31), 900000)
    due = {d.property.reference: d for d in programme.programme(YEAR_END)}
    assert set(due) == {"S1"}  # the hall was valued four years ago; investment property every year
    _accepted(setup["hall"], "operational", date(2022, 3, 31), 3900000).delete()
    Valuation.objects.filter(property=setup["hall"]).update(valuation_date=date(2022, 3, 31))
    assert {d.property.reference for d in programme.programme(YEAR_END)} == {"H1", "S1"}
    client.post("/valuations/", {"action": "start", "year": "2027-03-31", "valuer": setup["valuer"].pk})
    instructed = Valuation.objects.filter(valuation_date=YEAR_END)
    assert instructed.count() == 2 and all(v.case.case_type.code == "asset_valuation" for v in instructed)
    assert Case.objects.filter(case_type__code="valuation_programme").count() == 1
    client.post("/valuations/", {"action": "start", "year": "2027-03-31"})  # not twice
    assert Valuation.objects.filter(valuation_date=YEAR_END).count() == 2


def test_recording_and_accepting(client, setup):
    Classification.objects.create(property=setup["hall"], asset_class=AssetClass.objects.get(code="operational"),
                                  effective_from=date(2021, 4, 1))
    client.force_login(setup["surveyor"])
    client.post(f"/valuations/property/{setup['hall'].pk}/", {"action": "new", "valuation_date": "2027-03-31"})
    v = Valuation.objects.get()
    url = v.get_absolute_url()
    base = {"action": "save", "basis": "drc", "purpose": "Financial statements (CIPFA Code)",
            "valuation_date": "2027-03-31", "valuer": setup["valuer"].pk, "value": "4000000",
            "land_value": "500000", "building_value": "3000000"}
    response = client.post(url, base)
    assert "must add up" in response.content.decode()
    base.update(building_value="3500000", terms_agreed_on="2026-10-01", report_date="2027-04-15",
                material_uncertainty="on")
    response = client.post(url, base)
    assert "statement of material uncertainty" in response.content.decode()
    base.pop("material_uncertainty")
    base["report"] = SimpleUploadedFile("report.pdf", b"%PDF-1.4 report")
    client.post(url, base)
    v.refresh_from_db()
    assert v.status == "received" and v.value == Decimal("4000000") and v.report
    client.post(url, {"action": "accept"})
    v.refresh_from_db()
    assert v.status == "received"  # only administrators accept
    client.force_login(setup["admin"])
    client.post(url, {"action": "accept"})
    v.refresh_from_db()
    assert v.status == "received"  # over the componentisation threshold with no components
    client.post(url, {"action": "component", "name": "Roof", "value": "800000", "useful_life": "20"})
    client.post(url, {"action": "accept"})
    v.refresh_from_db()
    assert v.status == "accepted" and v.accepted_by == setup["admin"]
    client.force_login(setup["surveyor"])
    assert client.post(url, base).status_code == 403  # accepted valuations are locked


def test_impairment_prompts_open_a_case(client, setup):
    Classification.objects.create(property=setup["shops"], asset_class=AssetClass.objects.get(code="investment"),
                                  effective_from=date(2021, 4, 1))
    _accepted(setup["shops"], "investment", date(2026, 3, 31), 900000)
    assert programme.prompts() == []
    setup["shops"].occupation = "vacant"
    setup["shops"].save()
    prompt = programme.prompts()[0]
    assert "Occupation changed" in prompt.reasons[0]
    client.force_login(setup["admin"])
    response = client.post("/valuations/", {"action": "review", "property": setup["shops"].pk})
    case = Case.objects.get(case_type__code="impairment")
    assert response["Location"] == case.get_absolute_url() and programme.prompts() == []


def test_downloads_import_and_pages(client, make_user, setup):
    Classification.objects.create(property=setup["shops"], asset_class=AssetClass.objects.get(code="investment"),
                                  effective_from=date(2021, 4, 1))
    _accepted(setup["shops"], "investment", date(2026, 3, 31), 900000)
    programme.start(YEAR_END, valuer=setup["valuer"])
    client.force_login(setup["admin"])
    assert client.get("/valuations/data-pack/?year=2027-03-31").status_code == 200
    assert client.get("/valuations/schedule/?year=2027-03-31").status_code == 200
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Valuations"
    ws.append(["Asset reference", "Valuation date", "Value", "Land", "Buildings", "Valuer"])
    ws.append(["S1", "31/03/2027", 950000, 250000, 700000, "A Valuer"])
    buf = io.BytesIO()
    wb.save(buf)
    response = client.post("/import/valuations/", {"file": SimpleUploadedFile("v.xlsx", buf.getvalue())})
    assert response.context["result"].ok, [r.errors for r in response.context["result"].rows]
    client.post("/import/valuations/", {"confirm": "1", "token": response.context["token"]})
    v = Valuation.objects.get(property=setup["shops"], valuation_date=YEAR_END)
    assert v.value == Decimal("950000") and v.status == "received"
    client.force_login(make_user("view", "Viewers"))
    for url in ("/valuations/", f"/valuations/property/{setup['shops'].pk}/", v.get_absolute_url(),
                v.case.get_absolute_url(), "/"):
        assert client.get(url).status_code == 200, url
    assert client.post("/valuations/", {"action": "classify"}).status_code == 403


def test_demo(db):
    from django.core.management import call_command

    call_command("load_demo_data", verbosity=0)
    assert Valuation.objects.filter(status="received").count() == 2
    assert programme.prompts()
    call_command("load_demo_data", "--reset", verbosity=0)
    assert Valuer.objects.count() == 2
