# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demonstration examples of the commercial features added on 25 November 2026: index terms on the CPI leases, a
completed assignment with an AGA, rent deposit accounts, interest terms, a payment plan, ITZA on the shops in The
Precinct and Market Square, a marketing case with an agent instructed for a vacant shop, and IFRS 16 notes on the
leases the council holds.

All fictional. Index figures are not loaded: a test site fetches the real ones from the ONS each night."""
from datetime import date, timedelta
from decimal import Decimal

from apps.core.dates import add_months

D = Decimal
NOTE = "Fictional demonstration party."
MARKETING_MARK = "DEMO-MKT"

# Shops: (reference, internal width m, depth m, other areas [(label, m², divisor)])
SHOPS = [
    ("DM-N02-U01", "6.5", "16.9", [("Rear storage", "12", "10")]),
    ("DM-N02-U02", "5", "16", []),
    ("DM-N02-U03", "5", "16", []),
    ("DM-N02-U04", "5.5", "17.3", []),
    ("DM-N02-U05", "5", "16", []),
    ("DM-N02-U07", "5", "16", []),
    ("DM-S01-U02", "4.8", "15", []),
    ("DM-S01-U03", "4.8", "15", []),
    ("DM-S01-U05", "4.8", "15", []),
]


def _party(name, ptype="company"):
    from .models import Party

    party, _ = Party.objects.get_or_create(name=name, defaults={"party_type": ptype, "notes": NOTE,
                                                                "address": "1 Example Street, Exampleton ZZ99 1AA"})
    return party


def load(today=None):
    today = today or date.today()
    _index_terms()
    _itza()
    _dealings(today)
    _deposits(today)
    _ledger(today)
    _marketing(today)
    _ifrs16()


def _ifrs16():
    """IFRS 16 notes on the two leases the council holds, as finance would record them."""
    from .models import Lease

    Lease.objects.filter(reference="DL-0100").update(
        ifrs16_notes="Peppercorn ground lease: right-of-use asset at current value, no lease liability.")
    Lease.objects.filter(reference="DL-0530").update(
        ifrs16_notes="Council not reasonably certain to use its break: full term used.")


def _index_terms():
    from .models import IndexSeries, Lease

    cpi = IndexSeries.objects.filter(code="CPI").first()
    for lease in Lease.objects.filter(reference__in=("DL-0005", "DL-0508"), review_basis="cpi"):
        last_review = lease.rent_schedule.filter(reason__in=("index", "review")).order_by("-effective_from").first()
        start = last_review.effective_from if last_review else lease.term_start
        lease.index_series, lease.index_lag_months = cpi, 3
        lease.index_base_month = add_months(start, -3).replace(day=1)
        lease.index_cap_pct, lease.index_collar_pct = D("4"), D("1")
        lease.index_compounded, lease.index_upward_only = True, True
        lease.save()


def _itza():
    from apps.properties import itza
    from apps.properties.models import Property

    for ref, width, depth, others in SHOPS:
        prop = Property.objects.filter(reference=ref).first()
        if prop is None:
            continue
        spec = {"zone_depth": "6.1", "mode": "rectangle", "width": width, "depth": depth,
                "others": [{"label": label, "area": area, "divisor": divisor} for label, area, divisor in others]}
        result = itza.calculate(spec)
        if result.ok:
            prop.itza_sqm, prop.itza_zone_depth_m, prop.itza_workings = result.total, result.zone_depth, spec
            prop.itza_measured_on, prop.itza_notes = date(2026, 6, 1), "Zoned from the shop front at 6.1 m."
            prop.save(update_fields=["itza_sqm", "itza_zone_depth_m", "itza_workings", "itza_measured_on",
                                     "itza_notes"])


def _dealings(today):
    """2 The Precinct was assigned a few months ago, with an AGA from the outgoing tenant."""
    from apps.cases.models import Case

    from . import dealings
    from .models import Dealing, Lease

    for case in Case.objects.filter(case_type__code__in=dealings.CASE_KINDS, lease__isnull=False):
        dealings.from_case(case)  # the demo cases were decided directly, so bring their dealings up to date
    lease = Lease.objects.filter(reference="DL-0512").first()
    if lease is None or lease.dealings.filter(kind=Dealing.Kind.ASSIGNMENT, status="completed").exists():
        return
    assignee = lease.counterparty
    former = _party("Northfield Newsagents Ltd")
    lease.counterparty = former
    lease.save()
    completed = max(lease.term_start + timedelta(days=60), today - timedelta(days=120))
    dealing = Dealing.objects.create(lease=lease, kind=Dealing.Kind.ASSIGNMENT, status=Dealing.Status.CONSENTED,
                                     to_party=assignee, aga=True, consent_on=completed - timedelta(days=21),
                                     notes="Business sold as a going concern.")
    dealings.complete(dealing, completed_on=completed)
    lease.refresh_from_db()  # complete() changed the tenant
    lease.assignment_terms = lease.underletting_terms = Lease.AlienationTerms.CONSENT
    lease.aga_on_assignment = True
    lease.save()


def _deposits(today):
    from .models import DepositEntry, Lease

    for ref, entries in (
        ("DL-0502", [("received", 0, "9750", "Deposit on completion"), ("interest", 12, "286.31", "Year 1"),
                     ("interest", 24, "301.12", "Year 2"), ("interest_paid", 24, "587.43", "Paid to the tenant")]),
        ("DL-0003", [("received", 0, "13000", "Deposit on completion"),
                     ("drawdown", None, "3250", "Unpaid March quarter's rent")]),
    ):
        lease = Lease.objects.filter(reference=ref).first()
        if lease is None or lease.deposit_entries.exists():
            continue
        lease.deposit_deed_date = lease.term_start
        lease.save(update_fields=["deposit_deed_date"])
        for kind, months, amount, notes in entries:
            when = add_months(lease.term_start, months) if months is not None else today - timedelta(days=40)
            DepositEntry.objects.create(lease=lease, date=min(when, today), kind=kind, amount=D(amount),
                                        notes=notes)


def _ledger(today):
    from apps.core.models import ModuleSettings

    from .models import Lease

    for lease in Lease.objects.filter(reference__in=("DL-0511", "DL-0512", "DL-0514", "DL-0515", "DL-0518")):
        lease.interest_basis, lease.interest_margin_pct, lease.interest_grace_days = "fixed", D("8"), 14
        lease.save(update_fields=["interest_basis", "interest_margin_pct", "interest_grace_days"])
    if not ModuleSettings.load().rent_ledger_enabled:
        return
    from apps.ledger import billing, creditcontrol

    launderette = Lease.objects.filter(reference="DL-0518").first()
    if launderette is not None and not launderette.chase_actions.exists():
        from apps.ledger.models import ChaseStage

        account = billing.account(launderette, today)
        start = creditcontrol.episode_start(account, today)
        if start is not None:
            letters = ChaseStage.objects.filter(days_overdue__lte=(today - start).days, action="letter")
            for stage in letters:  # the arrears case is left as the next step
                creditcontrol.take(launderette, stage, today=min(today, start + timedelta(days=stage.days_overdue)),
                                   account=account)
    pizza = Lease.objects.filter(reference="DL-0016").first()
    if pizza is not None and not pizza.payment_plans.exists():
        owed = billing.account(pizza, today).overdue
        if owed > 0:
            creditcontrol.make_plan(pizza, today - timedelta(days=7), owed, 6, today + timedelta(days=7),
                                    notes="Agreed by phone with the director; instalments by standing order.")


def _marketing(today):
    from apps.cases import workflow
    from apps.cases.models import AgentInstruction, Case, CaseType
    from apps.properties.models import Property

    prop = Property.objects.filter(reference="DM-N02-U03").first()
    case_type = CaseType.objects.filter(code="marketing").first()
    if prop is None or case_type is None or Case.objects.filter(crm_reference=MARKETING_MARK).exists():
        return
    case = workflow.open_case(case_type, title="Market 3 The Precinct to let", property=prop,
                              received_on=today - timedelta(days=70), how_received=Case.Received.OTHER,
                              crm_reference=MARKETING_MARK)
    AgentInstruction.objects.create(
        case=case, agent=_party("Exampleton Commercial LLP", "llp"), basis=AgentInstruction.Basis.SOLE,
        instructed_on=today - timedelta(days=60), expires_on=today + timedelta(days=12), fee_pct=D("10"),
        fee_notes="of the first year's rent, plus VAT, on completion", asking_rent=D("11000"),
        terms="New lease for 5 years or more, tenant's full repairing and insuring", board=True)
