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
              ("DL-0034", "DM-S07-U04", "Exampleton Code Works Ltd", 19200, -5)]
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
    _documents()
    return Lease.objects.filter(reference__startswith="DL-").count()


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
            file=ContentFile(placeholder_pdf(f"Lease - {lease.counterparty.name}", lines, banner), name="lease.pdf"))
        if ref == "DL-0004":
            LeaseDocument.objects.create(
                lease=lease, document_type="notice", description="Section 25 notice (landlord's)",
                document_date=lease.term_end,
                file=ContentFile(placeholder_pdf("Landlord's notice under section 25", [
                    "Landlord and Tenant Act 1954, section 25 (demonstration only).",
                    f"Tenant: {lease.counterparty.name}", "The landlord does not oppose a new tenancy."], banner),
                    name="s25.pdf"))


def remove():
    Lease.objects.filter(reference__startswith="DL-").delete()
    Party.objects.filter(notes="Fictional demonstration party.", leases__isnull=True, guarantees__isnull=True).delete()
