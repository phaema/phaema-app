# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portfolios: each council's own list, on properties, in the register's filters, reports, imports and the API."""
import pytest
from django.urls import reverse

from apps.core.roles import ADMINISTRATORS, VIEWERS
from apps.properties.models import Portfolio, Property
from apps.reports import datasets


@pytest.fixture
def props(db):
    leisure = Portfolio.objects.get(name="Leisure")
    asc = Portfolio.objects.get(name="Adult social care")
    a = Property.objects.create(reference="P1", name="Pool", property_type="building", portfolio=leisure)
    b = Property.objects.create(reference="P2", name="Day centre", property_type="building", portfolio=asc)
    c = Property.objects.create(reference="P3", name="Field", property_type="land")
    return leisure, asc, a, b, c


def test_starting_list_is_there(db):
    names = set(Portfolio.objects.values_list("name", flat=True))
    assert {"Investment", "Leisure", "Children's services", "Adult social care"} <= names
    assert list(Portfolio.objects.values_list("name", flat=True))[0] == "Investment"  # ordered


def test_register_filters_by_portfolio(client, make_user, props):
    leisure, _asc, *_ = props
    client.force_login(make_user("v", VIEWERS))
    url = reverse("properties:list")
    names = [p.name for p in client.get(url, {"portfolio": leisure.pk}).context["page_obj"]]
    assert names == ["Pool"]
    assert [p.name for p in client.get(url, {"portfolio": "none"}).context["page_obj"]] == ["Field"]
    page = client.get(url)
    assert b"Adult social care" in page.content  # filter option and column
    detail = client.get(props[2].get_absolute_url())
    assert b"Leisure" in detail.content


def test_report_column_and_filter(props):
    leisure, asc, *_ = props
    ds = datasets.get("properties")
    field = ds.field("portfolio")
    assert (str(asc.pk), "Adult social care") in field.options
    qs = datasets.apply_filters(ds, ds.queryset(), {"portfolio": {"in": [str(leisure.pk)]}})
    assert [field.value(p) for p in qs] == ["Leisure"]


def test_new_portfolio_appears_without_restart(props):
    Portfolio.objects.create(name="Coroner's service")
    assert any(name == "Coroner's service" for _v, name in datasets.get("properties").field("portfolio").options)


def test_api_filter(client, make_user, props):
    leisure, *_ = props
    client.force_login(make_user("v", VIEWERS))
    data = client.get("/api/properties/", {"portfolio": leisure.pk}).json()
    rows = data["results"] if isinstance(data, dict) else data
    assert [r["reference"] for r in rows] == ["P1"] and rows[0]["portfolio_name"] == "Leisure"


def test_import_sets_portfolio_by_name(db):
    from apps.properties import importer

    rows = [(2, {"reference": "IMP1", "name": "Care home", "property_type": "Building",
                 "portfolio": "adult social care"}),
            (3, {"reference": "IMP2", "name": "Mystery", "property_type": "Building", "portfolio": "Nonsense"})]
    result, prepared = importer.validate(rows)
    assert not result.rows[0].errors
    assert any("No portfolio called" in e for e in result.rows[1].errors)
    importer.apply([prepared[0]])
    assert Property.objects.get(reference="IMP1").portfolio.name == "Adult social care"


def test_cannot_delete_portfolio_in_use(client, make_user, props):
    leisure, *_ = props
    client.force_login(make_user("a", ADMINISTRATORS))
    response = client.get(reverse("admin:properties_portfolio_delete", args=[leisure.pk]))
    assert response.status_code == 403
    spare = Portfolio.objects.create(name="Spare")
    assert client.get(reverse("admin:properties_portfolio_delete", args=[spare.pk])).status_code == 200
