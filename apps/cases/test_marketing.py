# SPDX-License-Identifier: AGPL-3.0-or-later
"""Marketing a vacant property: the case type, agent instructions, and the particulars and instruction letter."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.cases import workflow
from apps.cases.models import AgentInstruction, CaseType
from apps.documents import merge
from apps.documents.models import DocumentTemplate
from apps.documents.render import fill
from apps.leases.models import Party
from apps.properties.models import Property


@pytest.fixture
def surveyor(make_user):
    return make_user("sue", "Surveyors", email="sue@example.org")


@pytest.fixture
def case(db, surveyor):
    unit = Property.objects.create(reference="U8", name="Unit 8", property_type="unit", managing_surveyor=surveyor,
                                   address_line_1="8 Mill Lane", town="Exampleton", postcode="EX1 1AA",
                                   nia_sqm=Decimal("120.5"), occupation="vacant", available_from=date(2026, 9, 1))
    return workflow.open_case(CaseType.objects.get(code="marketing"), title="Market Unit 8", property=unit)


def test_marketing_case_type_ships_with_its_tasks(case):
    tasks = [t.description for t in case.tasks.all()]
    assert any("Instruct the agent" in t for t in tasks) and any("new letting case" in t for t in tasks)


def test_instructing_an_agent_from_the_case_page(case, surveyor, client):
    client.force_login(surveyor)
    response = client.post(case.get_absolute_url(), {
        "action": "save_instruction", "basis": "sole", "new_agent": "Example Property Agents LLP",
        "instructed_on": "2026-08-01", "expires_on": "2026-11-01", "fee_pct": "10", "fee_notes": "plus VAT",
        "asking_rent": "14,500", "terms": "New full repairing lease, 5 years or more", "board": "1"})
    assert response.status_code == 302
    instruction = AgentInstruction.objects.get(case=case)
    assert instruction.agent.name == "Example Property Agents LLP" and instruction.asking_rent == Decimal("14500")
    assert instruction.fee_text == "10% (plus VAT)" and instruction.board
    page = client.get(case.get_absolute_url()).content.decode()
    assert "Marketing and agents" in page and "Example Property Agents LLP" in page


def test_instruction_needs_an_agent_unless_in_house(case, surveyor, client):
    client.force_login(surveyor)
    client.post(case.get_absolute_url(), {"action": "save_instruction", "basis": "sole"})
    assert not AgentInstruction.objects.exists()
    client.post(case.get_absolute_url(), {"action": "save_instruction", "basis": "in_house"})
    assert AgentInstruction.objects.get().agent is None


def test_ending_and_expiry_warning(case, surveyor, client):
    agent = Party.objects.create(name="Agents Ltd", party_type="company")
    instruction = AgentInstruction.objects.create(case=case, agent=agent, instructed_on=date.today(),
                                                  expires_on=date.today() + timedelta(days=10))
    client.force_login(surveyor)
    assert "the instruction ends on" in client.get(case.get_absolute_url()).content.decode()
    client.post(case.get_absolute_url(), {"action": "end_instruction", "instruction": instruction.pk, "status": "let"})
    instruction.refresh_from_db()
    assert instruction.status == "let" and instruction.ended_on == date.today()


def test_particulars_and_instruction_letter_use_the_property_and_instruction(case):
    agent = Party.objects.create(name="Agents Ltd", party_type="company", address="1 High Street\nExampleton")
    AgentInstruction.objects.create(case=case, agent=agent, instructed_on=date(2026, 8, 1),
                                    asking_rent=Decimal("14500"), fee_pct=Decimal("10"), terms="New lease")
    values = merge.context(case=case)
    assert values["agent_name"] == "Agents Ltd" and values["asking_rent"] == "£14,500.00"
    assert values["property_nia"].startswith("120.5 m²") and values["property_available_from"] == "1 September 2026"
    particulars = DocumentTemplate.objects.get(code="marketing-particulars")
    text = fill(particulars, values, particulars.extra_fields)
    assert "Unit 8" in text and "£14,500.00 a year" in text and "To let" in text and "Agents Ltd" in text
    letter = DocumentTemplate.objects.get(code="agent-instruction")
    assert "sole agency" in fill(letter, values, letter.extra_fields)


def test_viewers_cannot_instruct(case, make_user, client):
    client.force_login(make_user("vic", "Viewers"))
    assert client.post(case.get_absolute_url(), {"action": "save_instruction", "basis": "in_house"}).status_code == 403
