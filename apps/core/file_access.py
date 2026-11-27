# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who may open an uploaded file: the person must be able to open the record the file belongs to.

Every stored file is looked up to the record that holds it, and the record's module decides: files in core PHAEMA
(properties, titles, leases, cases) open for everyone with a role, as the records do; files held by an optional
module (valuations, compliance, maintenance) open only for people who can use that module, with the module switched
on. A file that belongs to no record (an import being checked, a searchable copy of a scan, anything left over) is
never served, and neither is a file held by a model not listed here, so a new kind of file stays closed until it is
given a rule. Project papers are served by the project pages, which check that the person can see the project.
"""
from django.apps import apps
from django.db import models

# model label -> the module a person needs ("" for core PHAEMA, everyone with a role)
RULES = {
    "properties.PropertyPhoto": "",
    "properties.PropertyPlan": "",
    "properties.TitleDocument": "",
    "leases.LeaseDocument": "",
    "cases.Correspondence": "",
    "cases.CaseDocument": "",
    "cases.SiteVisitPhoto": "",
    "maintenance.JobDocument": "maintenance",
    "maintenance.RepairPhoto": "maintenance",
    "compliance.Certificate": "compliance",
    "compliance.BuildingDocument": "compliance",
    "valuations.Valuation": "valuations",
    "valuations.AuditReview": "valuations",
}
SERVED_ELSEWHERE = {"projects.GatewayDecision", "projects.ProjectDocument"}


def file_fields():
    """Every file and image field in PHAEMA, as (model, field name)."""
    return [(model, field.name) for model in apps.get_models() for field in model._meta.get_fields()
            if isinstance(field, models.FileField)]


def owner(path):
    """The record that holds the stored file, or None."""
    for model, name in file_fields():
        item = model._default_manager.filter(**{name: path}).first()
        if item is not None:
            return item
    return None


def may_open(user, path):
    """True if this person may open the stored file at `path`."""
    from .access import can_use
    from .roles import has_role

    if not has_role(user):
        return False
    item = owner(path)
    if item is None:
        return False
    label = item._meta.label
    if label in SERVED_ELSEWHERE or label not in RULES:
        return False
    module = RULES[label]
    return not module or can_use(user, module)
