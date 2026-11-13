# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fictional tenants and agreements for the Exampleton demonstration estate.

All names are invented ("Exampleton ..."), company numbers use a ZZ prefix that
Companies House does not issue, emails use example.org and phone numbers come from
Ofcom's range reserved for drama (01632 960xxx). Dates are set relative to today so
that the key-date warnings always show a realistic mix.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.core.dates import add_months
from apps.properties.models import Property

from .models import BreakOption, Lease, Party


def quarter_day_on_or_before(d):
    """The English quarter day (25 Mar, 24 Jun, 29 Sep, 25 Dec) on or before d."""
    candidates = [date(y, m, dd) for y in (d.year - 1, d.year) for m, dd in ((3, 25), (6, 24), (9, 29), (12, 25))]
    return max(c for c in candidates if c <= d)


PARTIES = [
    ("Exampleton Precision Engineering Ltd", "company", "ZZ000101", "", "Dana Hughes"),
    ("Exampleton Print Co Ltd", "company", "ZZ000102", "", "Lee Patel"),
    ("Exampleton Logistics Ltd", "company", "ZZ000103", "", "Morgan Reid"),
    ("Exampleton Holdings plc", "company", "ZZ000104", "", "Company Secretary"),
    ("Brookside Joinery", "partnership", "", "", "Sam and Jo Carter"),
    ("Exampleton Fine Foods Ltd", "company", "ZZ000105", "", "Ravi Singh"),
    ("Exampleton Motor Repairs", "sole_trader", "", "", "Chris Evans"),
    ("Exampleton Couriers Ltd", "company", "ZZ000106", "", "Alex Kim"),
    ("The Corner Café, Exampleton", "sole_trader", "", "", "Maria Rossi"),
    ("Exampleton Books Ltd", "company", "ZZ000107", "", "Tom Green"),
    ("Exampleton Hair Studio", "sole_trader", "", "", "Jade Wilson"),
    ("Exampleton Gifts Ltd", "company", "ZZ000108", "", "Nina Shah"),
    ("Exampleton Pizza Ltd", "company", "ZZ000109", "", "Luca Bianchi"),
    ("Exampleton Lettings Ltd", "company", "ZZ000110", "", "Grace Hall"),
    ("Brookside Community Association", "charity", "", "ZZ1000001", "Margaret Lee"),
    ("Exampleton Allotment Society", "charity", "", "ZZ1000002", "Peter Brown"),
    ("Example & Sons (Farmers)", "partnership", "", "", "John Example"),
    ("Exampleton Riverside Refreshments", "sole_trader", "", "", "Ben Taylor"),
    ("Exampleton Design Studio Ltd", "company", "ZZ000111", "", "Kim Adams"),
    ("Exampleton Accountancy Services", "sole_trader", "", "", "Priti Rao"),
    ("Exampleton Code Works Ltd", "company", "ZZ000112", "", "Owen Price"),
    ("Exampleton Estates Ltd", "company", "ZZ000113", "", "Estates Manager"),
    ("Exampleton Power Networks plc", "company", "ZZ000114", "", "Wayleaves Team"),
]


def load(today=None):
    today = today or date.today()
    parties = {}
    for i, (name, ptype, co, charity, contact) in enumerate(PARTIES, start=1):
        slug = name.lower().replace(" ", ".").replace(",", "").replace("&", "and").replace("(", "").replace(")", "")[:40]
        parties[name], _ = Party.objects.update_or_create(name=name, defaults={
            "party_type": ptype, "company_number": co, "charity_number": charity, "contact_name": contact,
            "email": f"{slug}@example.org", "phone": f"01632 960{100 + i:03d}",
            "address": "c/o the demised premises, Exampleton ZZ99 1AA",
            "finance_customer_ref": f"DMC{10000 + i}",
            "notes": "Fictional demonstration party.",
        })
    P = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-")}
    q = quarter_day_on_or_before(today)

    def lease(ref, props, party, **kw):
        obj, _ = Lease.objects.update_or_create(reference=ref, defaults={"counterparty": parties[party], **kw})
        obj.properties.set([P[r] for r in props])
        obj.breaks.all().delete()
        return obj

    # Riverside Industrial Estate
    start = add_months(q, -57)  # rent review due in about 3 months
    lease("DL-0001", ["DM-E01-U01"], "Exampleton Precision Engineering Ltd", agreement_type="lease",
          lease_date=start, term_start=start, term_end=add_months(start, 120) - timedelta(days=1),
          security_of_tenure="inside", annual_rent=Decimal("28800"), rent_frequency="quarter_days",
          vat_chargeable=True, review_basis="om_up", review_interval_years=5, next_review_date=add_months(start, 60),
          repairing="fri", insurance="landlord_recharged", service_charge_payable=True,
          permitted_use="Light industrial (Class E(g)(iii))", alienation="Assignment of the whole with consent. No subletting.")
    start = add_months(q, -55)
    lease("DL-0002", ["DM-E01-U02"], "Exampleton Print Co Ltd", agreement_type="lease", lease_date=start,
          term_start=start, term_end=add_months(start, 60) - timedelta(days=1), security_of_tenure="contracted_out",
          annual_rent=Decimal("26400"), vat_chargeable=True, review_basis="none", repairing="fri",
          insurance="landlord_recharged", service_charge_payable=True, permitted_use="Printing and light industrial")
    start = add_months(q, -106)
    l3 = lease("DL-0003", ["DM-E01-U04"], "Exampleton Logistics Ltd", agreement_type="lease", lease_date=start,
               term_start=start, term_end=add_months(start, 180) - timedelta(days=1), security_of_tenure="inside",
               guarantor=parties["Exampleton Holdings plc"], annual_rent=Decimal("52000"), vat_chargeable=True,
               review_basis="om_up", review_interval_years=5, next_review_date=add_months(start, 120),
               repairing="fri", insurance="landlord_recharged", service_charge_payable=True,
               permitted_use="Storage and distribution (Class B8)", deposit=Decimal("13000"))
    BreakOption.objects.create(lease=l3, break_date=add_months(start, 120), exercisable_by="tenant", notice_months=6,
                               conditions="Rent paid up to date and vacant possession given.")
    start = add_months(q, -62)
    lease("DL-0004", ["DM-E01-U05"], "Brookside Joinery", agreement_type="lease", status="holding_over",
          lease_date=start, term_start=start, term_end=add_months(start, 60) - timedelta(days=1),
          security_of_tenure="inside", annual_rent=Decimal("17600"), vat_chargeable=True, review_basis="none",
          repairing="fri", insurance="landlord_recharged", service_charge_payable=True,
          notes="Holding over since expiry. Renewal under the 1954 Act being negotiated.")
    start = add_months(q, -17)
    lease("DL-0005", ["DM-E01-U06"], "Exampleton Fine Foods Ltd", agreement_type="lease", lease_date=start,
          term_start=start, term_end=add_months(start, 72) - timedelta(days=1), security_of_tenure="inside",
          annual_rent=Decimal("18720"), vat_chargeable=True, review_basis="cpi", review_interval_years=1,
          next_review_date=add_months(start, 24), repairing="fri", insurance="landlord_recharged",
          service_charge_payable=True, permitted_use="Food preparation and storage")
    start = add_months(q, -14)
    lease("DL-0006", ["DM-E01-U07"], "Exampleton Motor Repairs", agreement_type="lease", lease_date=start,
          term_start=start, term_end=add_months(start, 36) - timedelta(days=1), security_of_tenure="contracted_out",
          annual_rent=Decimal("16000"), vat_chargeable=True, review_basis="none", repairing="iri",
          insurance="landlord_recharged", service_charge_payable=True, permitted_use="Vehicle repairs (Class B2)")
    start = add_months(q, -60)
    lease("DL-0007", ["DM-E01-U03"], "Exampleton Couriers Ltd", agreement_type="lease", status="ended",
          lease_date=start, term_start=start, term_end=add_months(start, 60) - timedelta(days=1),
          actual_end=add_months(q, -3), security_of_tenure="contracted_out", annual_rent=Decimal("24000"),
          vat_chargeable=True, review_basis="none", repairing="fri", insurance="landlord_recharged",
          notes="Ended at expiry. Dilapidations claim being prepared.")

    # Market Square
    shops = [("DL-0011", "DM-S01-U01", "The Corner Café, Exampleton", 14500, -30, 120, "om_up", 5, 60, "inside"),
             ("DL-0012", "DM-S01-U02", "Exampleton Books Ltd", 12000, -8, 60, "none", None, None, "contracted_out"),
             ("DL-0014", "DM-S01-U04", "Exampleton Hair Studio", 10500, -40, 120, "om_up", 5, 60, "inside"),
             ("DL-0015", "DM-S01-U05", "Exampleton Gifts Ltd", 11800, -20, 36, "none", None, None, "contracted_out"),
             ("DL-0016", "DM-S01-U06", "Exampleton Pizza Ltd", 15500, -70, 120, "om_up", 5, 60, "inside")]
    for ref, unit, party, rent, offset, months, basis, every, review_at, sec in shops:
        start = add_months(q, offset)
        lease(ref, [unit], party, agreement_type="lease", lease_date=start, term_start=start,
              term_end=add_months(start, months) - timedelta(days=1), security_of_tenure=sec,
              annual_rent=Decimal(rent), review_basis=basis, review_interval_years=every,
              next_review_date=add_months(start, review_at) if review_at else None,
              repairing="iri", insurance="landlord_recharged", service_charge_payable=True,
              permitted_use=P[unit].use_description)
    start = add_months(q, -26)
    l17 = lease("DL-0017", ["DM-S01-U07"], "Exampleton Lettings Ltd", agreement_type="lease", lease_date=start,
                term_start=start, term_end=add_months(start, 72) - timedelta(days=1), security_of_tenure="inside",
                annual_rent=Decimal("19500"), vat_chargeable=True, review_basis="om_up", review_interval_years=3,
                next_review_date=add_months(start, 36), repairing="iri", insurance="landlord_recharged",
                service_charge_payable=True, permitted_use="Offices (Class E(g)(i))")
    BreakOption.objects.create(lease=l17, break_date=add_months(start, 36), exercisable_by="either", notice_months=6)

    # Community, farm and kiosk
    start = date(2012, 4, 1)
    lease("DL-0021", ["DM-S05"], "Brookside Community Association", agreement_type="lease", lease_date=start,
          term_start=start, term_end=date(2037, 3, 31), security_of_tenure="contracted_out", annual_rent=Decimal("0"),
          rent_frequency="peppercorn", review_basis="none", repairing="fri", insurance="tenant",
          permitted_use="Community centre", notes="Peppercorn rent; community asset lease.")
    start = add_months(q, -40)
    lease("DL-0022", ["DM-S08"], "Exampleton Allotment Society", agreement_type="lease", lease_date=start,
          term_start=start, term_end=add_months(start, 120) - timedelta(days=1), security_of_tenure="na",
          annual_rent=Decimal("1200"), rent_frequency="annually", review_basis="none",
          permitted_use="Allotment gardens", notes="Society self-manages the 46 plots.")
    start = date(today.year if today >= date(today.year, 10, 11) else today.year - 1, 10, 11)
    lease("DL-0023", ["DM-S10"], "Example & Sons (Farmers)", agreement_type="fbt", lease_date=start,
          term_start=start, term_end=add_months(start, 12) - timedelta(days=1), security_of_tenure="na",
          annual_rent=Decimal("3150"), rent_frequency="annually", review_basis="none",
          permitted_use="Grazing only", notes="One-year farm business tenancy, renewed each Michaelmas.")
    start = add_months(q, -18)
    lease("DL-0024", ["DM-S11"], "Exampleton Riverside Refreshments", agreement_type="licence", lease_date=start,
          term_start=start, term_end=add_months(start, 36) - timedelta(days=1), security_of_tenure="na",
          annual_rent=Decimal("6500"), rent_frequency="monthly", review_basis="none", repairing="landlord",
          permitted_use="Sale of hot and cold refreshments")

    # Enterprise Centre suites and the head lease held by the council
    suites = [("DL-0031", "DM-S07-U01", "Exampleton Design Studio Ltd", 8100, -10),
              ("DL-0032", "DM-S07-U02", "Exampleton Accountancy Services", 8100, -22),
              ("DL-0034", "DM-S07-U04", "Exampleton Code Works Ltd", 9600, -5)]  # 50% first-year concession
    for ref, unit, party, rent, offset in suites:
        start = add_months(q, offset)
        lease(ref, [unit], party, agreement_type="lease", lease_date=start, term_start=start,
              term_end=add_months(start, 36) - timedelta(days=1), security_of_tenure="contracted_out",
              annual_rent=Decimal(rent), rent_frequency="monthly", vat_chargeable=True, review_basis="none",
              repairing="landlord", insurance="landlord_recharged", service_charge_payable=True,
              permitted_use="Offices", alienation="No assignment or subletting.")
    lease("DL-0100", ["DM-S07"], "Exampleton Estates Ltd", direction="in", agreement_type="lease",
          lease_date=date(2004, 6, 24), term_start=date(2004, 6, 24), term_end=date(2129, 6, 23),
          security_of_tenure="inside", annual_rent=Decimal("0"), rent_frequency="peppercorn", review_basis="none",
          repairing="fri", insurance="tenant", notes="Ground lease held by the council; see title ZZ200001.")
    lease("DL-0200", ["DM-E01-L01"], "Exampleton Power Networks plc", agreement_type="wayleave",
          lease_date=date(1998, 1, 1), term_start=date(1998, 1, 1), term_end=None, security_of_tenure="na",
          annual_rent=Decimal("250"), rent_frequency="annually", review_basis="none",
          premises_description="Underground cable route beneath the estate roads",
          notes="Terminable wayleave, 12 months' notice.")
    # A tenancy at will while a new lease is agreed, so the dashboard has one to show.
    start = add_months(q, -4)
    lease("DL-0040", ["DM-S11"], "Exampleton Riverside Refreshments", agreement_type="taw", lease_date=start,
          term_start=start, term_end=None, security_of_tenure="na", annual_rent=Decimal("1800"),
          rent_frequency="monthly", review_basis="none", repairing="landlord",
          premises_description="Seasonal seating area next to the kiosk",
          notes="Tenancy at will while the licence for the seating area is agreed.")
    _documents()
    _rent_histories(q)
    _management_flags(today)
    return Lease.objects.filter(reference__startswith="DL-").count()


def _management_flags(today):
    """Examples of the lease management flags: time of the essence, an estimated rental value, demands on
    hold, a billing contact, arrears passed to debt collectors and an insurance certificate to review."""
    from .models import LeaseEvent
    from .workflow import sync_events

    def get(ref):
        return Lease.objects.filter(reference=ref).first()

    lease = get("DL-0001")  # rent review due in about three months
    if lease:
        lease.time_of_essence = True
        lease.billing_contact_name = "Accounts payable"
        lease.billing_email = "accounts.payable@example.org"
        lease.billing_address = "Finance Department, Exampleton Precision Engineering Ltd, PO Box 1, Exampleton ZZ99 9ZZ"
        lease.save()
        sync_events(lease, today)
        LeaseEvent.objects.filter(lease=lease, event_type="review", status__in=("open", "in_progress")).update(
            estimated_rental_value=Decimal("32500"))
    lease = get("DL-0004")  # expiring: a renewal to value
    if lease:
        sync_events(lease, today)
        LeaseEvent.objects.filter(lease=lease, event_type="expiry", status__in=("open", "in_progress")).update(
            estimated_rental_value=(lease.annual_rent * Decimal("1.1")).quantize(Decimal("100")))
    lease = get("DL-0031")
    if lease:
        lease.demands_on_hold = True
        lease.demands_on_hold_reason = "Rent query with the tenant: on hold until the meeting"
        lease.save()
    lease = get("DL-0024")
    if lease:
        lease.arrears_referral = "debt"
        lease.arrears_referred_on = today - timedelta(days=21)
        lease.arrears_referral_reference = "DEMO-DCA-0042"
        lease.save()


def _schedule(lease, entries):
    from . import workflow
    from .models import RentScheduleEntry

    lease.rent_schedule.all().delete()
    for when, rent, reason, notes in entries:
        RentScheduleEntry.objects.create(lease=lease, effective_from=when, annual_rent=Decimal(rent),
                                         reason=reason, notes=notes)
    workflow.refresh_current_rent(lease)


def _rent_histories(q):
    from .models import LeaseEvent

    # DL-0003: initial rent, then a review at year 5 settled by agreement.
    l3 = Lease.objects.get(reference="DL-0003")
    review5 = add_months(l3.term_start, 60)
    _schedule(l3, [(l3.term_start, 46000, "initial", ""),
                   (review5, 52000, "review", "Settled by agreement")])
    LeaseEvent.objects.get_or_create(
        lease=l3, source="review", due_date=review5,
        defaults={"event_type": "review", "status": "done", "completed_on": add_months(review5, 2),
                  "assigned_to": l3.properties.first().managing_surveyor,
                  "outcome": f"Review settled at £52,000.00 a year from {review5:%d %B %Y}. Settled by agreement."})
    # DL-0034: half rent for the first year as a letting incentive, then the full rent.
    l34 = Lease.objects.get(reference="DL-0034")
    _schedule(l34, [(l34.term_start, 9600, "variation", "50% rent concession for the first year"),
                    (add_months(l34.term_start, 12), 19200, "step", "Full rent")])
    # DL-0005: CPI review at year 1 applied.
    l5 = Lease.objects.get(reference="DL-0005")
    _schedule(l5, [(l5.term_start, 18000, "initial", ""),
                   (add_months(l5.term_start, 12), 18720, "index", "CPI 4.0% applied")])


def _documents():
    from django.core.files.base import ContentFile

    from apps.properties.demo_media import placeholder_pdf

    from .models import LeaseDocument

    banner = "FICTIONAL DEMONSTRATION DOCUMENT - NOT A REAL LEASE"
    for ref in ("DL-0001", "DL-0003", "DL-0004", "DL-0021"):
        lease = Lease.objects.get(reference=ref)
        if lease.documents.exists():
            continue
        lines = [f"Agreement reference {lease.reference}", "Landlord: Demonstration District Council",
                 f"Tenant: {lease.counterparty.name}",
                 f"Premises: {'; '.join(p.name for p in lease.properties.all())}",
                 f"Term: {lease.term_description} from {lease.term_start:%d %B %Y}",
                 f"Rent: £{lease.annual_rent:,.2f} a year", f"Repairing: {lease.get_repairing_display()}"]
        LeaseDocument.objects.create(
            lease=lease, document_type="lease", description=f"Signed lease {lease.reference}",
            document_date=lease.lease_date,
            file=ContentFile(placeholder_pdf(f"Lease - {lease.counterparty.name}", lines, banner, more=_lease_pages(lease)),
                             name="lease.pdf"))
        if ref == "DL-0004":
            LeaseDocument.objects.create(
                lease=lease, document_type="notice", description="Section 25 notice (landlord's)",
                document_date=lease.term_end,
                file=ContentFile(placeholder_pdf("Landlord's notice under section 25", [
                    "Landlord and Tenant Act 1954, section 25 (demonstration only).",
                    f"Tenant: {lease.counterparty.name}", "The landlord does not oppose a new tenancy."], banner),
                    name="s25.pdf"))
    lease = Lease.objects.filter(reference="DL-0021").first()  # the tenant insures: a certificate about to run out
    if lease and not lease.documents.filter(document_type="insurance").exists():
        today = date.today()
        LeaseDocument.objects.create(
            lease=lease, document_type="insurance", description="Tenant's buildings insurance certificate",
            document_date=today - timedelta(days=330), review_date=today + timedelta(days=35),
            file=ContentFile(placeholder_pdf("Certificate of insurance", [
                f"Insured: {lease.counterparty.name}", "Buildings insurance, reinstatement value basis.",
                "Interest noted: Demonstration District Council (landlord)."], banner), name="insurance.pdf"))


def remove():
    Lease.objects.filter(reference__startswith="DL-").delete()
    Party.objects.filter(notes="Fictional demonstration party.", leases__isnull=True, guarantees__isnull=True).delete()


def _lease_pages(lease):
    """Further pages for a demonstration lease, so the PDF reader has several pages and wording to search."""
    return [
        ("1. Tenant's covenants", [
            "1.1  To pay the rent by equal quarterly payments in advance on the usual quarter days.",
            "1.2  To pay all rates, taxes and outgoings charged on the premises.",
            f"1.3  Repair: {lease.get_repairing_display()}.",
            "1.4  Not to make structural alterations. Not to make other alterations without the",
            "     landlord's written consent, which is not to be unreasonably withheld.",
            "1.5  Not to assign or underlet the whole without the landlord's written consent.",
            "1.6  Not to assign or underlet part only.",
            "1.7  To use the premises only for the permitted use.",
            "1.8  To yield up the premises at the end of the term in the condition this lease requires.",
        ]),
        ("2. Landlord's covenants", [
            "2.1  Quiet enjoyment: the tenant may hold the premises without interruption by the landlord.",
            "2.2  To insure the building against the insured risks and to reinstate after damage.",
            "2.3  To maintain the estate roads, landscaping and shared services, subject to the",
            "     tenant paying a fair proportion through the service charge.",
        ]),
        ("3. Rent review, break and forfeiture", [
            "3.1  The rent is reviewed to open market rent on each review date, upwards only.",
            "3.2  Time is not of the essence for the review, except where this lease says so.",
            "3.3  Any break right is exercised by written notice of not less than six months.",
            "3.4  The landlord may re-enter if rent is unpaid for 21 days or a covenant is broken.",
            "",
            "Schedule: the premises are shown edged red on the plan (not reproduced in this demonstration).",
        ]),
    ]
