# SPDX-License-Identifier: AGPL-3.0-or-later
import csv
import io
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from openpyxl import load_workbook

from apps.leases.models import Lease
from apps.properties.models import Property
from apps.reports import datasets, export
from apps.reports.models import Report


@pytest.fixture
def demo(db):
    call_command("load_demo_data", verbosity=0)


@pytest.fixture
def admin(make_user):
    return make_user("admin1", "Administrators")


@pytest.fixture
def surveyor(make_user):
    return make_user("surv1", "Surveyors")


@pytest.fixture
def viewer(make_user):
    return make_user("view1", "Viewers")


def _xlsx(response):
    return load_workbook(io.BytesIO(b"".join(response.streaming_content) if response.streaming else response.content))


def test_starter_reports_exist(db):
    keys = set(Report.objects.exclude(starter="").values_list("starter", flat=True))
    assert {"rent_roll", "expiries_12m", "vacant", "overdue_events", "terrier", "tenant_contacts"} <= keys


def test_every_starter_runs_and_downloads(client, viewer, demo):
    client.force_login(viewer)
    for report in Report.objects.exclude(starter=""):
        assert client.get(report.get_absolute_url()).status_code == 200
        response = client.get(report.get_absolute_url() + "?format=xlsx")
        assert response.status_code == 200
        sheet = _xlsx(response).active
        assert sheet.max_row >= 1
        assert client.get(report.get_absolute_url() + "?format=csv").status_code == 200


def test_filters(demo):
    ds = datasets.get("leases")
    qs = ds.queryset()
    expensive = datasets.apply_filters(ds, qs, {"annual_rent": {"min": 50000}})
    assert expensive.exists() and all(lease.annual_rent >= 50000 for lease in expensive)
    soon = datasets.apply_filters(ds, qs, {"term_end": {"next_days": 365}})
    limit = date.today() + timedelta(days=365)
    assert all(date.today() <= lease.term_end <= limit for lease in soon)
    current = datasets.apply_filters(ds, qs, {"status": {"in": ["current"]}})
    assert set(current.values_list("status", flat=True)) <= {"current"}
    named = datasets.apply_filters(ds, qs, {"reference": {"contains": "DL-"}})
    assert named.count() == Lease.objects.filter(reference__icontains="DL-").count()


def test_build_save_and_run_report(client, surveyor, demo):
    client.force_login(surveyor)
    response = client.post("/reports/new/?dataset=properties", {
        "name": "Big vacant shops", "col_reference": "1", "col_name": "1", "pos_name": "1", "pos_reference": "2",
        "col_nia_sqm": "1", "f_nia_sqm_min": "100", "sort_by": "nia_sqm", "sort_descending": "1",
        "show_totals": "1",
    })
    report = Report.objects.get(name="Big vacant shops")
    assert response.status_code == 302 and report.owner == surveyor
    assert report.columns == ["name", "reference", "nia_sqm"]
    assert report.filters == {"nia_sqm": {"min": 100.0}}
    page = client.get(report.get_absolute_url())
    assert page.status_code == 200
    expected = Property.objects.filter(nia_sqm__gte=100).count()
    assert page.context["count"] == expected
    sheet = _xlsx(client.get(report.get_absolute_url() + "?format=xlsx")).active
    assert [c.value for c in sheet[1]] == ["Name", "Reference", "NIA (m²)"] or sheet.cell(1, 1).value == "Name"
    assert sheet.max_row == expected + 2  # header, rows, totals


def test_report_needs_name_and_column(client, surveyor, db):
    client.force_login(surveyor)
    response = client.post("/reports/new/?dataset=leases", {"name": ""})
    assert response.status_code == 200
    assert len(response.context["errors"]) == 2
    assert not Report.objects.filter(starter="", owner=surveyor).exists()


def test_report_privacy_and_permissions(client, surveyor, viewer, admin, db):
    private = Report.objects.create(name="Mine", dataset="leases", columns=["reference"], owner=surveyor)
    shared = Report.objects.create(name="Ours", dataset="leases", columns=["reference"], owner=surveyor, shared=True)
    starter = Report.objects.exclude(starter="").first()
    client.force_login(viewer)
    assert client.get(private.get_absolute_url()).status_code == 404
    assert client.get(shared.get_absolute_url()).status_code == 200
    assert client.get(f"/reports/{shared.pk}/edit/").status_code == 403
    assert client.post(f"/reports/{shared.pk}/delete/").status_code == 403
    # Anyone can copy a report they can see, and the copy is theirs.
    client.post(f"/reports/{shared.pk}/copy/")
    assert Report.objects.get(name="Copy of Ours").owner == viewer
    client.force_login(surveyor)
    assert client.get(f"/reports/{starter.pk}/edit/").status_code == 403
    client.force_login(admin)
    assert client.get(f"/reports/{starter.pk}/edit/").status_code == 200
    assert client.post(f"/reports/{starter.pk}/delete/").status_code == 403
    assert client.post(f"/reports/{private.pk}/delete/").status_code == 302
    assert not Report.objects.filter(pk=private.pk).exists()


def test_list_exports_follow_filters(client, viewer, demo):
    client.force_login(viewer)
    response = client.get("/properties/?occupation=vacant&format=csv")
    assert response.status_code == 200
    text = b"".join(response.streaming_content).decode("utf-8-sig") if response.streaming else \
        response.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert len(rows) - 1 == Property.objects.filter(occupation="vacant").count()
    for url in ("/leases/?format=xlsx", "/leases/events/?format=xlsx", "/leases/parties/?format=xlsx",
                "/changes/?format=xlsx"):
        assert client.get(url).status_code == 200, url


def test_csv_guards_against_formulae():
    assert export._clean("=SUM(A1)") == "'=SUM(A1)"
    assert export._clean("+44 1632") == "'+44 1632"
    assert export._clean("Normal") == "Normal"


def test_themes(client, viewer, db):
    client.force_login(viewer)
    response = client.get("/theme/dark/", HTTP_REFERER="/properties/")
    assert response.status_code == 302 and response.cookies["phaema_theme"].value == "dark"
    assert 'data-theme="dark"' in client.get("/").content.decode()
    client.get("/theme/nonsense/")
    assert 'data-theme="dark"' in client.get("/").content.decode()
