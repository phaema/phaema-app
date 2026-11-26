# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uploaded files open only for people who can open the record they belong to, even with the address."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client

from apps.core import file_access as files
from apps.core.models import AccessArea, ModuleSettings
from apps.properties.models import Property, PropertyPlan

pytestmark = pytest.mark.own_areas

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _person(username, role="Surveyors", areas=()):
    user = User.objects.create_user(username, password="a-long-test-password")
    user.groups.add(Group.objects.get(name=role))
    user.access_areas.set(AccessArea.objects.filter(code__in=areas))
    return User.objects.get(pk=user.pk)


def _client(user):
    client = Client(HTTP_HOST="localhost")
    client.force_login(user)
    return client


@pytest.fixture
def held(db):
    """One file in each module: a property plan (core), a job document, a certificate, a building document,
    a valuation report and audit evidence."""
    from apps.compliance.models import BuildingDocument, Certificate, ComplianceType, Requirement
    from apps.maintenance.models import Job, JobDocument
    from apps.valuations.models import AssetClass, AuditReview, Valuation

    settings = ModuleSettings.load()
    settings.maintenance_enabled = settings.compliance_enabled = settings.valuation_enabled = True
    settings.save()
    hall = Property.objects.create(reference="T-1", name="Market Hall")

    def attach(item, field="file"):
        getattr(item, field).save("paper.pdf", ContentFile(PDF), save=True)
        return getattr(item, field).name

    plan = attach(PropertyPlan(property=hall, title="Ground floor"))
    job = Job.objects.create(property=hall, title="Fix the roof")
    job_doc = attach(JobDocument(job=job, description="Quote"))
    req = Requirement.objects.create(property=hall, kind=ComplianceType.objects.get(code="epc"))
    certificate = attach(Certificate(requirement=req, issued_on=date(2025, 3, 2), expires_on=date(2035, 3, 2)))
    building = attach(BuildingDocument(property=hall, category=BuildingDocument.Category.choices[0][0], title="O&M"))
    valuation = Valuation.objects.create(property=hall, asset_class=AssetClass.objects.get(code="investment"),
                                         valuation_date=date(2026, 3, 31), basis="euv", value=Decimal("900000"))
    report = attach(valuation, "report")
    evidence = attach(AuditReview(valuation=valuation, accounts_year="2025/26"), "evidence")
    return {"plan": plan, "maintenance": [job_doc], "compliance": [certificate, building],
            "valuations": [report, evidence]}


def test_every_kind_of_file_has_a_rule():
    for model, _name in files.file_fields():
        label = model._meta.label
        assert label in files.RULES or label in files.SERVED_ELSEWHERE, f"{label} needs a rule in core/file_access.py"


def test_core_files_open_for_everyone_with_a_role(held):
    for role in ("Administrators", "Surveyors", "Contributors", "Viewers"):
        user = _person(f"u.{role.lower()}", role)
        assert _client(user).get(f"/files/{held['plan']}?raw=1").status_code == 200


@pytest.mark.parametrize("module,area", [("maintenance", "maintenance"), ("compliance", "maintenance"),
                                         ("valuations", "valuation")])
def test_module_files_need_the_module(held, module, area):
    outsider = _client(_person("no.area"))
    insider = _client(_person("in.area", areas=[area]))
    for path in held[module]:
        assert outsider.get(f"/files/{path}?raw=1").status_code == 404
        assert outsider.get(f"/files/{path}?download=1").status_code == 404
        assert outsider.get(f"/files/{path}", HTTP_ACCEPT="text/html").status_code == 404  # nor the viewer page
        assert insider.get(f"/files/{path}?raw=1").status_code == 200


def test_administrators_open_module_files_only_while_the_module_is_on(held):
    admin = _client(_person("ann", "Administrators"))
    path = held["valuations"][0]
    assert admin.get(f"/files/{path}?raw=1").status_code == 200
    settings = ModuleSettings.load()
    settings.valuation_enabled = False
    settings.save()
    assert admin.get(f"/files/{path}?raw=1").status_code == 404


def test_files_without_a_record_are_never_served(db):
    user = _client(_person("ann", "Administrators"))
    loose = default_storage.save("imports/upload.xlsx", ContentFile(b"PK\x03\x04"))
    assert user.get(f"/files/{loose}").status_code == 404
    assert user.get("/files/plans/none.pdf").status_code == 404
