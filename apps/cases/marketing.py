# SPDX-License-Identifier: AGPL-3.0-or-later
"""Marketing a vacant property: agent instructions on a marketing case, and the details for particulars."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils.dateparse import parse_date

from .models import AgentInstruction

CODE = "marketing"


def applies(case):
    return case.case_type.code == CODE or case.instructions.exists()


def context(case, today=None):
    if not applies(case):
        return {}
    today = today or date.today()
    from apps.leases.models import Party

    instructions = list(case.instructions.select_related("agent"))
    return {
        "marketing": True, "instructions": instructions,
        "expiring": [i for i in instructions if i.expiring(today)],
        "bases": AgentInstruction.Basis.choices, "instruction_statuses": AgentInstruction.Status.choices,
        "agents": Party.objects.filter(party_type__in=["company", "llp", "partnership", "sole_trader"]).order_by("name")
        if case.is_open else [],
    }


def _decimal(text):
    text = (text or "").replace(",", "").replace("£", "").replace("%", "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{text} is not a number.")
    if value < 0:
        raise ValueError("Amounts cannot be negative.")
    return value


def save_instruction(case, post):
    """Add an instruction from the case page. Raises ValueError with a message to show."""
    from apps.leases.models import Party

    basis = post.get("basis", AgentInstruction.Basis.SOLE)
    if basis not in AgentInstruction.Basis.values:
        raise ValueError("Choose the basis of the instruction.")
    agent = None
    if basis != AgentInstruction.Basis.IN_HOUSE:
        agent = Party.objects.filter(pk=post.get("agent") or 0).first()
        new_name = post.get("new_agent", "").strip()
        if agent is None and new_name:
            agent = Party.objects.create(name=new_name[:200], party_type="company",
                                         notes="Added as a marketing agent.")
        if agent is None:
            raise ValueError("Choose the agent, or enter a new agent's name.")
    instructed = parse_date(post.get("instructed_on", "") or "") or date.today()
    expires = parse_date(post.get("expires_on", "") or "")
    if expires and expires < instructed:
        raise ValueError("The instruction cannot end before it starts.")
    return AgentInstruction.objects.create(
        case=case, agent=agent, basis=basis, instructed_on=instructed, expires_on=expires,
        fee_pct=_decimal(post.get("fee_pct")), fee_fixed=_decimal(post.get("fee_fixed")),
        fee_notes=post.get("fee_notes", "")[:255], asking_rent=_decimal(post.get("asking_rent")),
        asking_price=_decimal(post.get("asking_price")), terms=post.get("terms", "")[:255],
        board=post.get("board") == "1", notes=post.get("notes", "")[:2000])


def end_instruction(case, post):
    instruction = case.instructions.filter(pk=post.get("instruction") or 0).first()
    if instruction is None:
        raise ValueError("That instruction was not found on this case.")
    status = post.get("status", AgentInstruction.Status.EXPIRED)
    if status not in (AgentInstruction.Status.LET, AgentInstruction.Status.WITHDRAWN, AgentInstruction.Status.EXPIRED):
        raise ValueError("Choose how the instruction ended.")
    instruction.status = status
    instruction.ended_on = parse_date(post.get("ended_on", "") or "") or date.today()
    instruction.save(update_fields=["status", "ended_on", "updated_at"])
    return instruction


def merge_fields(case):
    """Details of the current (or latest) instruction, for the particulars and the instruction letter."""
    from apps.documents.merge import _address, money

    instruction = (case.instructions.filter(status=AgentInstruction.Status.ACTIVE).select_related("agent").first()
                   or case.instructions.select_related("agent").first())
    if instruction is None:
        return {}
    agent = instruction.agent
    return {
        "agent_name": agent.name if agent else "", "agent_address": _address(agent) if agent else "",
        "agent_basis": instruction.get_basis_display().lower(), "agent_fee": instruction.fee_text,
        "instruction_ends": instruction.expires_on.strftime("%-d %B %Y") if instruction.expires_on else "",
        "asking_rent": money(instruction.asking_rent) if instruction.asking_rent is not None else "",
        "asking_price": money(instruction.asking_price) if instruction.asking_price is not None else "",
        "terms_offered": instruction.terms,
    }
