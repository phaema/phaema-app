# SPDX-License-Identifier: AGPL-3.0-or-later
"""A second fictional district, Northfield, which roughly doubles the demonstration data.

Like Exampleton, everything is invented: ZZ98 pseudo-postcodes, 9999… UPRNs, ZZ title numbers, ZZ company
numbers, example.org emails and Ofcom's drama telephone range. References keep the DM- (property), DL- (agreement)
and DEMO (cases, contractors, valuers) prefixes, so `load_demo_data --reset` removes Northfield with the rest.

Each function is called by load_demo_data at the point where the matching Exampleton data is loaded.
"""
from datetime import date, timedelta
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

TOWN = "Northfield"
DX, DY = 2600, 1700  # Northfield sits north-east of Exampleton on the map

SURVEYORS = {"demo.lchen": ("Lena", "Chen"), "demo.rbaker": ("Rob", "Baker")}
ASSIGNMENTS = {
    "DM-N01": "demo.lchen", "DM-N07": "demo.lchen", "DM-N10": "demo.lchen", "DM-N12": "demo.lchen",
    "DM-N02": "demo.rbaker", "DM-N05": "demo.rbaker", "DM-N08": "demo.rbaker", "DM-N09": "demo.rbaker",
    "DM-N03": "demo.ojones", "DM-N04": "demo.ojones", "DM-N11": "demo.ojones",
    # DM-N06 is left unassigned, like DM-S06 and DM-S10.
}


def add_records(add, rect):
    """Add Northfield's properties to the demo property list, parents before children."""
    from .management.commands.load_demo_data import uprn

    def r(dx, dy, w, h):
        return rect(DX + dx, DY + dy, w, h)

    def put(ref, name, ptype, parent=None, **fields):
        fields.setdefault("town", TOWN)
        add(ref, name, ptype, parent, **fields)

    # 1. Northfield Business Park: estate > two blocks > ten units, and the estate roads
    put("DM-N01", "Northfield Business Park", "estate", holding_purpose="investment", tenure="freehold",
        occupation="part_let", use_description="Business park", address_line_1="Enterprise Road", postcode="ZZ98 1BP",
        usrn="99980001", boundary=r(0, 0, 380, 220),
        notes="Business park built by the council in 2008, let on a mix of protected and contracted-out leases.")
    blocks = {"B01": ("Hangar block", 20, 20, [("01", "let", 650), ("02", "let", 650), ("03", "let", 650),
                                               ("04", "vacant", 650), ("05", "let", 1300)]),
              "B02": ("Workshop block", 20, 130, [("06", "let", 240), ("07", "let", 240), ("08", "let", 240),
                                                  ("09", "let", 240), ("10", "vacant", 480)])}
    for bref, (bname, bx, by, units) in blocks.items():
        block = f"DM-N01-{bref}"
        put(block, bname, "building", "DM-N01", holding_purpose="investment", tenure="freehold",
            occupation="part_let", use_description="Industrial and warehouse", use_class="B8",
            address_line_1=f"{bname}, Enterprise Road", postcode="ZZ98 1BP",
            gia_sqm=D(sum(u[2] for u in units)) * D("1.08"), boundary=r(bx, by, 68 * len(units), 70))
        for i, (num, occ, nia) in enumerate(units):
            put(f"DM-N01-U{num}", f"Unit {int(num)}, Northfield Business Park", "unit", block, uprn=uprn(),
                holding_purpose="investment", tenure="freehold", occupation=occ,
                use_description="Warehouse" if nia >= 600 else "Workshop",
                use_class="B8" if nia >= 600 else "E(g)(iii)", address_line_1=f"Unit {int(num)}, Enterprise Road",
                postcode="ZZ98 1BP", nia_sqm=D(nia), gia_sqm=D(nia) * D("1.05"), boundary=r(bx + 68 * i, by, 68, 70))
    put("DM-N01-L01", "Business park roads and verges", "land", "DM-N01", holding_purpose="operational",
        tenure="freehold", occupation="na", use_description="Estate roads", boundary=r(0, 95, 380, 30),
        site_hazards="HGV movements all day. Wear high-visibility clothing and keep to the footpath.")

    # 2. The Precinct: eight shops with offices over
    put("DM-N02", "Northfield Precinct", "site", holding_purpose="investment", tenure="freehold",
        occupation="part_let", use_description="Shopping precinct", address_line_1="The Precinct",
        postcode="ZZ98 2PR", usrn="99980002", boundary=r(500, 300, 170, 50))
    put("DM-N02-B01", "1–8 The Precinct", "building", "DM-N02", uprn=uprn(), holding_purpose="investment",
        tenure="freehold", occupation="part_let", use_description="Shops with offices over",
        address_line_1="1–8 The Precinct", postcode="ZZ98 2PR", gia_sqm=D("1620"), boundary=r(500, 300, 170, 30))
    shops = [("Pharmacy", "let", 110), ("Shop", "let", 80), ("Shop", "vacant", 80), ("Bakery", "let", 95),
             ("Shop", "let", 80), ("Café", "let", 105), ("Shop", "vacant", 80), ("Launderette", "let", 90)]
    classes = {"Shop": "E(a)", "Pharmacy": "E(a)", "Bakery": "E(a)", "Café": "E(b)", "Launderette": "E(c)"}
    for i, (use, occ, nia) in enumerate(shops, start=1):
        put(f"DM-N02-U0{i}", f"{i} The Precinct", "unit", "DM-N02-B01", uprn=uprn(), holding_purpose="investment",
            tenure="freehold", occupation=occ, use_description=use, use_class=classes[use],
            address_line_1=f"{i} The Precinct", postcode="ZZ98 2PR", nia_sqm=D(nia), gia_sqm=D(nia) * D("1.1"),
            boundary=r(500 + 21 * (i - 1), 300, 21, 30))
    put("DM-N02-U09", "Upper floors, 1–8 The Precinct", "unit", "DM-N02-B01", uprn=uprn(),
        holding_purpose="investment", tenure="freehold", occupation="let", use_description="Offices",
        use_class="E(g)(i)", address_line_1="Upper floors, The Precinct", postcode="ZZ98 2PR", nia_sqm=D("520"))

    # 3. Operational, community, surplus and other land
    put("DM-N03", "Northfield Library", "building", uprn=uprn(), holding_purpose="operational", tenure="freehold",
        occupation="council", use_description="Public library", use_class="F1(d)", address_line_1="Library Square",
        postcode="ZZ98 3LS", gia_sqm=D("1180"), boundary=r(420, 420, 45, 35),
        site_hazards="Asbestos insulating board in the first floor ceiling void: do not disturb. Check the register.",
        notes="1960s library with a community meeting room. Listed as an asset of community value (fictional).")
    put("DM-N04", "Northfield Leisure Centre", "building", uprn=uprn(), holding_purpose="community",
        tenure="freehold", occupation="let", use_description="Leisure centre with pool", use_class="F2(c)",
        address_line_1="Park Road", postcode="ZZ98 3PR", gia_sqm=D("5400"), boundary=r(700, 420, 110, 70),
        site_hazards="Pool plant room: chemical store and confined space. Visits by arrangement with the duty manager.",
        notes="Run by Northfield Leisure Trust on a 30-year lease at a peppercorn, with an annual management fee.")
    put("DM-N05", "Northfield Community Hall", "building", uprn=uprn(), holding_purpose="community",
        tenure="freehold", occupation="let", use_description="Community hall", use_class="F2(b)",
        address_line_1="Church Lane", postcode="ZZ98 4CL", gia_sqm=D("410"), boundary=r(300, 600, 35, 25))
    put("DM-N06", "Former Northfield bus depot", "land", holding_purpose="surplus", tenure="freehold",
        occupation="vacant", use_description="Cleared brownfield site", address_line_1="Depot Road",
        postcode="ZZ98 5DR", boundary=r(-300, 300, 160, 120),
        site_hazards="Unsecured excavations and possible ground contamination. Do not enter without the site key holder.",
        notes="Declared surplus. Ground investigation found hydrocarbons near the former fuel tanks.")
    put("DM-N07", "Water tower telecoms site", "land", holding_purpose="investment", tenure="freehold",
        occupation="let", use_description="Telecommunications mast", address_line_1="Tower Hill",
        postcode="ZZ98 6TH", boundary=r(-100, 600, 20, 20),
        notes="Code agreement under the Electronic Communications Code (fictional operator).")
    put("DM-N08", "Northfield Park pavilion and pitches", "land", holding_purpose="community", tenure="freehold",
        occupation="let", use_description="Sports pitches and changing pavilion", address_line_1="Park Road",
        postcode="ZZ98 3PR", boundary=r(820, 420, 200, 140))
    put("DM-N09", "Northfield Market Hall", "building", uprn=uprn(), holding_purpose="investment",
        tenure="freehold", occupation="let", use_description="Covered market", use_class="Sui generis",
        address_line_1="Market Street", postcode="ZZ98 2MS", gia_sqm=D("2100"), boundary=r(560, 380, 60, 35),
        notes="Victorian market hall, Grade II listed. Let to a market operator who licenses the stalls.")
    put("DM-N10", "Hilltop Farm", "land", holding_purpose="investment", tenure="freehold", occupation="let",
        use_description="Mixed farm (72 hectares)", address_line_1="Hilltop Lane", postcode="ZZ98 7HL",
        boundary=r(-1100, 900, 700, 500), notes="County farms estate holding, let on a farm business tenancy.")
    put("DM-N11", "Kingsway car park", "site", uprn=uprn(), holding_purpose="operational", tenure="freehold",
        occupation="council", use_description="Surface car park (180 spaces)", address_line_1="Kingsway",
        postcode="ZZ98 2KW", boundary=r(680, 300, 80, 50))
    put("DM-N12", "Northfield Innovation Hub", "building", uprn=uprn(), holding_purpose="investment",
        tenure="leasehold", occupation="part_let", use_description="Start-up offices", use_class="E(g)(i)",
        address_line_1="Station Approach", postcode="ZZ98 8SA", gia_sqm=D("640"), boundary=r(380, 520, 30, 25),
        notes="Leased in by the council from a private landlord for ten years, sub-let to new businesses.")
    for i, (occ, nia) in enumerate([("let", 85), ("vacant", 85)], start=1):
        put(f"DM-N12-U0{i}", f"Studio {i}, Innovation Hub", "unit", "DM-N12", uprn=uprn(),
            holding_purpose="investment", tenure="leasehold", occupation=occ, use_description="Office studio",
            use_class="E(g)(i)", address_line_1=f"Studio {i}, Station Approach", postcode="ZZ98 8SA", nia_sqm=D(nia))


TITLES = [
    {"title_number": "ZZ100011", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Digital copy only", "refs": ["DM-N01"],
     "restrictions_and_covenants": "Covenant to maintain a landscaped buffer along the northern boundary."},
    {"title_number": "ZZ100012", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 301", "refs": ["DM-N02", "DM-N09", "DM-N11"]},
    {"title_number": "ZZ100013", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 302", "refs": ["DM-N03", "DM-N04", "DM-N08"],
     "restrictions_and_covenants": "Park land held for public recreation: disposal needs advertising under s123(2A)."},
    {"title_number": None, "tenure": "freehold", "title_class": "unregistered",
     "deeds_location": "Legal Services strongroom, packet 44 (conveyance 1931)", "refs": ["DM-N05"]},
    {"title_number": "ZZ100014", "tenure": "freehold", "title_class": "qualified",
     "deeds_location": "Digital copy only", "refs": ["DM-N06"],
     "restrictions_and_covenants": "Qualified title: the 1952 conveyance is missing. Title insurance on disposal."},
    {"title_number": "ZZ100015", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "County farms archive", "refs": ["DM-N07", "DM-N10"]},
    {"title_number": "ZZ200011", "tenure": "leasehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 330", "refs": ["DM-N12"],
     "restrictions_and_covenants": "10-year lease; tenant's break at year 5 on six months' notice."},
]

PHOTOS = {
    "DM-N01": [("Northfield Business Park entrance", "industrial")],
    "DM-N01-U04": [("Unit 4 front elevation", "industrial"), ("Unit 4 interior", "industrial")],
    "DM-N02-B01": [("The Precinct from the square", "retail"), ("Shop fronts, north side", "retail")],
    "DM-N03": [("Northfield Library entrance", "civic")],
    "DM-N06": [("Former bus depot from Depot Road", "land"), ("Former fuel tank area", "land")],
}

PARTIES = [
    ("Northfield Freight Ltd", "company", "ZZ000201", "", "Hannah Ward"),
    ("Northfield Packaging Ltd", "company", "ZZ000202", "", "Imran Ali"),
    ("Northfield Self Storage Ltd", "company", "ZZ000203", "", "Operations Manager"),
    ("Northfield Group plc", "company", "ZZ000204", "", "Company Secretary"),
    ("Northfield Brewing Co Ltd", "company", "ZZ000205", "", "Sophie Turner"),
    ("Northfield Joinery Workshop", "sole_trader", "", "", "Mark Davies"),
    ("Northfield Bikes", "partnership", "", "", "Ana and Tom Field"),
    ("Northfield Ceramics Ltd", "company", "ZZ000206", "", "Ellie Moss"),
    ("Northfield Pharmacy Ltd", "company", "ZZ000207", "", "Raj Mehta"),
    ("Northfield News and Post", "sole_trader", "", "", "Gary Hunt"),
    ("Northfield Bakery", "partnership", "", "", "Ruth and Ian Baker"),
    ("Northfield Phone Repairs", "sole_trader", "", "", "Kai Wong"),
    ("Northfield Coffee House Ltd", "company", "ZZ000208", "", "Lucy Price"),
    ("Northfield Launderette", "sole_trader", "", "", "Olu Adeyemi"),
    ("Northfield Training Services Ltd", "company", "ZZ000209", "", "Centre Manager"),
    ("Northfield Leisure Trust", "charity", "", "ZZ1000011", "Chief Executive"),
    ("Northfield Community Association", "charity", "", "ZZ1000012", "Hall Bookings Secretary"),
    ("Example Mobile Networks Ltd", "company", "ZZ000210", "", "Estates Team"),
    ("Northfield Rovers Football Club", "charity", "", "ZZ1000013", "Club Secretary"),
    ("Northfield Markets Ltd", "company", "ZZ000211", "", "Market Manager"),
    ("Hilltop Farming Partnership", "partnership", "", "", "Beth and Dan Hill"),
    ("Northfield Apps Ltd", "company", "ZZ000212", "", "Founder"),
    ("Station Approach Properties Ltd", "company", "ZZ000213", "", "Asset Manager"),
]


def load_leases(today):
    """Northfield's 23 agreements, with dates relative to today so that reviews, breaks and expiries fall due
    at a realistic mix of times."""
    from apps.core.dates import add_months
    from apps.leases.demo import quarter_day_on_or_before
    from apps.leases.models import BreakOption, Lease, Party

    from .models import Property

    parties = {}
    for i, (name, ptype, co, charity, contact) in enumerate(PARTIES, start=1):
        slug = name.lower().replace(" ", ".").replace(",", "").replace("&", "and")[:40]
        parties[name], _ = Party.objects.update_or_create(name=name, defaults={
            "party_type": ptype, "company_number": co, "charity_number": charity, "contact_name": contact,
            "email": f"{slug}@example.org", "phone": f"01632 960{200 + i:03d}",
            "address": "c/o the demised premises, Northfield ZZ98 1AA", "finance_customer_ref": f"DMC{20000 + i}",
            "notes": "Fictional demonstration party."})
    P = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-N")}
    q = quarter_day_on_or_before(today)

    def lease(ref, props, party, offset, months, **kw):
        start = add_months(q, offset)
        kw.setdefault("lease_date", start)
        kw.setdefault("term_start", start)
        if months:
            kw.setdefault("term_end", add_months(start, months) - timedelta(days=1))
        obj, _ = Lease.objects.update_or_create(reference=ref, defaults={"counterparty": parties[party], **kw})
        obj.properties.set([P[r] for r in props])
        obj.breaks.all().delete()
        return obj

    park = dict(vat_chargeable=True, repairing="fri", insurance="landlord_recharged", service_charge_payable=True)
    lease("DL-0501", ["DM-N01-U01"], "Northfield Freight Ltd", -58, 120, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("41600"), review_basis="om_up", review_interval_years=5,
          next_review_date=add_months(add_months(q, -58), 60), permitted_use="Storage and distribution", **park)
    l2 = lease("DL-0502", ["DM-N01-U02"], "Northfield Packaging Ltd", -33, 120, agreement_type="lease",
               security_of_tenure="inside", annual_rent=D("39000"), review_basis="om_up", review_interval_years=5,
               next_review_date=add_months(add_months(q, -33), 60), deposit=D("9750"),
               deposit_held="Council rent deposit account", deposit_interest="Tenant, paid annually", **park)
    BreakOption.objects.create(lease=l2, break_date=add_months(add_months(q, -33), 60), exercisable_by="tenant",
                               notice_months=6, conditions="No material breach of the repairing covenant.")
    lease("DL-0503", ["DM-N01-U03"], "Northfield Self Storage Ltd", -110, 180, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("42250"), review_basis="rpi", review_interval_years=5,
          next_review_date=add_months(add_months(q, -110), 120), guarantor=parties["Northfield Group plc"],
          permitted_use="Self storage", **park)
    lease("DL-0505", ["DM-N01-U05"], "Northfield Brewing Co Ltd", -27, 180, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("78000"), review_basis="om_up", review_interval_years=5,
          next_review_date=add_months(add_months(q, -27), 60), permitted_use="Brewery and taproom (sui generis)",
          alienation="Assignment of the whole with consent; underletting of part not allowed.", **park)
    lease("DL-0506", ["DM-N01-U06"], "Northfield Joinery Workshop", -36, 36, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("14400"), rent_frequency="monthly", review_basis="none",
          **park)
    lease("DL-0507", ["DM-N01-U07"], "Northfield Bikes", -64, 60, agreement_type="lease", status="holding_over",
          security_of_tenure="inside", annual_rent=D("13200"), review_basis="none",
          notes="Holding over. The council intends to oppose renewal on ground (f) to redevelop the block.", **park)
    lease("DL-0508", ["DM-N01-U08"], "Northfield Ceramics Ltd", -9, 72, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("14800"), review_basis="cpi", review_interval_years=1,
          next_review_date=add_months(add_months(q, -9), 12), **park)
    lease("DL-0509", ["DM-N01-U09"], "Northfield Training Services Ltd", -47, 60, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("15600"), review_basis="none",
          permitted_use="Training centre (Class F1(a))", **park)
    lease("DL-0504", ["DM-N01-U04"], "Northfield Freight Ltd", -96, 96, agreement_type="lease", status="ended",
          actual_end=add_months(q, -2), security_of_tenure="contracted_out", annual_rent=D("36000"),
          review_basis="none", notes="Ended at expiry. Schedule of dilapidations served.", **park)

    shop = dict(repairing="iri", insurance="landlord_recharged", service_charge_payable=True)
    for ref, unit, party, rent, offset, months, basis, every, sec in [
            ("DL-0511", "DM-N02-U01", "Northfield Pharmacy Ltd", 21000, -44, 180, "om_up", 5, "inside"),
            ("DL-0512", "DM-N02-U02", "Northfield News and Post", 11500, -15, 60, "none", None, "contracted_out"),
            ("DL-0514", "DM-N02-U04", "Northfield Bakery", 13000, -52, 120, "om_up", 5, "inside"),
            ("DL-0515", "DM-N02-U05", "Northfield Phone Repairs", 10800, -6, 36, "none", None, "contracted_out"),
            ("DL-0516", "DM-N02-U06", "Northfield Coffee House Ltd", 16500, -23, 120, "om_up", 5, "inside"),
            ("DL-0518", "DM-N02-U08", "Northfield Launderette", 11000, -82, 120, "om_up", 5, "inside")]:
        start = add_months(q, offset)
        lease(ref, [unit], party, offset, months, agreement_type="lease", security_of_tenure=sec,
              annual_rent=D(rent), review_basis=basis, review_interval_years=every,
              next_review_date=add_months(start, 60) if every else None, permitted_use=P[unit].use_description,
              **shop)
    l19 = lease("DL-0519", ["DM-N02-U09"], "Northfield Training Services Ltd", -30, 72, agreement_type="lease",
                security_of_tenure="inside", annual_rent=D("23400"), vat_chargeable=True, review_basis="om_up",
                review_interval_years=3, next_review_date=add_months(add_months(q, -30), 36),
                permitted_use="Offices and training rooms", **shop)
    BreakOption.objects.create(lease=l19, break_date=add_months(add_months(q, -30), 36), exercisable_by="either",
                               notice_months=6)

    lease("DL-0520", ["DM-N04"], "Northfield Leisure Trust", -96, 360, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("0"), rent_frequency="peppercorn", review_basis="none",
          repairing="limited", insurance="landlord", permitted_use="Leisure centre and swimming pool",
          notes="Peppercorn lease with a separate management agreement; the council keeps structural repairs.")
    lease("DL-0521", ["DM-N05"], "Northfield Community Association", -20, 60, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("600"), rent_frequency="annually", review_basis="none",
          repairing="iri", insurance="landlord", permitted_use="Community hall")
    lease("DL-0522", ["DM-N07"], "Example Mobile Networks Ltd", -70, 120, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("4200"), rent_frequency="annually",
          review_basis="fixed", review_interval_years=5, next_review_date=add_months(add_months(q, -70), 60),
          repairing="other", insurance="tenant", premises_description="Compound and mast on the water tower site",
          notes="Code agreement; rent assessed on the no-network basis under the Electronic Communications Code.")
    lease("DL-0523", ["DM-N08"], "Northfield Rovers Football Club", -4, 12, agreement_type="licence",
          security_of_tenure="na", annual_rent=D("1800"), rent_frequency="annually", review_basis="none",
          repairing="landlord", permitted_use="Football matches and training, September to May")
    lease("DL-0524", ["DM-N09"], "Northfield Markets Ltd", -41, 180, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("34000"), review_basis="turnover", review_interval_years=1,
          next_review_date=add_months(add_months(q, -41), 48), repairing="iri", insurance="landlord_recharged",
          permitted_use="Covered market and ancillary café",
          notes="Base rent plus 8% of stall licence income above £300,000 a year.")
    start = date(today.year if today >= date(today.year, 3, 25) else today.year - 1, 3, 25)
    lease("DL-0525", ["DM-N10"], "Hilltop Farming Partnership", 0, 0, agreement_type="fbt", term_start=start,
          lease_date=start, term_end=date(start.year + 5, 3, 24), security_of_tenure="na", annual_rent=D("9800"),
          rent_frequency="annually", review_basis="om", review_interval_years=3,
          next_review_date=date(start.year + 3, 3, 25), repairing="other", insurance="tenant",
          permitted_use="Agriculture", notes="Five-year farm business tenancy, county farms starter holding.")
    lease("DL-0531", ["DM-N12-U01"], "Northfield Apps Ltd", -7, 24, agreement_type="licence",
          security_of_tenure="na", annual_rent=D("7200"), rent_frequency="monthly", vat_chargeable=True,
          review_basis="none", repairing="landlord", insurance="landlord", permitted_use="Offices",
          alienation="Personal to the licensee.")
    hub = lease("DL-0530", ["DM-N12"], "Station Approach Properties Ltd", -50, 120, direction="in",
                agreement_type="lease", security_of_tenure="contracted_out", annual_rent=D("38000"),
                review_basis="om_up", review_interval_years=5, next_review_date=add_months(add_months(q, -50), 60),
                repairing="fri", insurance="landlord_recharged", notes="Leased in by the council; see title ZZ200011.")
    BreakOption.objects.create(lease=hub, break_date=add_months(add_months(q, -50), 60), exercisable_by="tenant",
                               notice_months=6, conditions="Council's break: rent paid and vacant possession.")
    return Lease.objects.filter(reference__startswith="DL-05").count()


# Rent ledger: who has fallen behind in Northfield
UNPAID_LAST = {"DL-0506": 2, "DL-0512": 1, "DL-0518": 2}
PART_PAID = {"DL-0514": D("0.4")}

SERVICE = {
    "name": "Northfield Business Park services",
    "estate": "DM-N01",
    "members": ["DL-0501", "DL-0502", "DL-0503", "DL-0505", "DL-0506", "DL-0507", "DL-0508", "DL-0509"],
    "caps": {"DL-0509": D("1800.00")},
    "budget": {"MAN": 4200, "GRN": 7600, "ROAD": 5200, "SEC": 15800, "WASTE": 3300, "INS": 4100, "REP": 6400},
    "factor": {"MAN": 1, "GRN": 0.96, "ROAD": 1.41, "SEC": 1.02, "WASTE": 1.12, "INS": 1, "REP": 0.88},
    "description": "Gatehouse security, estate roads, landscaping, CCTV and shared waste for the business park. "
                   "Fictional demonstration data.",
}

# Valuation history for Northfield's top-level properties: (year, value, land, buildings, life, method)
VALUATION_HISTORY = {
    "DM-N01": (2026, 9400000, 2600000, 6800000, 32, "investment"),
    "DM-N02": (2026, 3850000, 1100000, 2750000, 28, "investment"),
    "DM-N03": (2023, 2150000, 380000, 1770000, 25, "drc"),
    "DM-N04": (2022, 8900000, 1200000, 7700000, 22, "drc"),
    "DM-N05": (2024, 420000, 110000, 310000, 30, "drc"),
    "DM-N06": (2026, 1250000, 1250000, 0, None, "residual"),
    "DM-N07": (2026, 62000, 62000, 0, None, "investment"),
    "DM-N09": (2026, 2900000, 500000, 2400000, 40, "investment"),
    "DM-N10": (2026, 1180000, 1180000, 0, None, "comparison"),
    "DM-N11": (2023, 760000, 760000, 0, None, "comparison"),
}


def surveyors():
    """Two more demonstration surveyors, supervised by the head of estates."""
    from apps.core.models import StaffProfile
    from apps.core.roles import SURVEYORS as ROLE

    users = {}
    for username, (first, last) in SURVEYORS.items():
        user, created = get_user_model().objects.get_or_create(username=username, defaults={
            "first_name": first, "last_name": last, "email": f"{username}@example.org"})
        if created:
            user.set_unusable_password()
            user.save()
        user.groups.add(Group.objects.get(name=ROLE))
        users[username] = user
    head = get_user_model().objects.filter(username="demo.head").first()
    if head:
        for user in users.values():
            StaffProfile.objects.update_or_create(user=user, defaults={"supervisor": head,
                                                                       "job_title": "Estates Surveyor"})
    return users


def load_cases(today):
    """Hand-made Northfield cases; lease event cases are opened automatically with Exampleton's."""
    from apps.cases import workflow
    from apps.cases.models import Approval, Case, CaseNote, CaseType, Correspondence
    from apps.leases.models import Lease, Party

    from .models import Property

    if Case.objects.filter(crm_reference__startswith="DEMO-N").exists():
        return 0
    surveyors()
    t = {c.code: c for c in CaseType.objects.all()}
    lease = {x.reference: x for x in Lease.objects.filter(reference__startswith="DL-05")}
    P = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-N")}
    head = get_user_model().objects.filter(username="demo.head").first()
    legal = get_user_model().objects.filter(username="demo.legal").first()
    made = 0

    def case(code, title, days_ago, n, **kw):
        nonlocal made
        made += 1
        return workflow.open_case(t[code], title=title, received_on=today - timedelta(days=days_ago),
                                  crm_reference=f"DEMO-N{n}", **kw)

    def tick(c, *starts):
        for task in c.tasks.all():
            if any(task.description.startswith(s) for s in starts):
                task.done_on, task.done_by = c.received_on + timedelta(days=4), c.owner
                task.save(update_fields=["done_on", "done_by"])

    def declare(c, details=""):
        c.conflict = "declared" if details else "none"
        c.conflict_details, c.conflict_by, c.conflict_on = details, c.owner, c.received_on + timedelta(days=5)
        c.save(update_fields=["conflict", "conflict_details", "conflict_by", "conflict_on"])

    # 1. Assignment of the brewery lease: just arrived, not yet acknowledged.
    c = case("assignment", "Consent to assign to Northfield Taproom Group Ltd", 3, 1, lease=lease["DL-0505"],
             how_received=Case.Received.EMAIL)
    Correspondence.objects.create(case=c, direction="in", method="email", on=c.received_on,
                                  correspondent="Northfield Brewing Co Ltd <accounts@example.org>",
                                  subject="Sale of the business: request for consent to assign",
                                  summary="We are selling the brewery to Northfield Taproom Group Ltd and ask for "
                                          "the council's consent to assign. Their management accounts are attached.")
    # 2. Change of use of a shop to a vape shop, refused with reasons.
    c = case("change_of_use", "Change of use of 2 The Precinct to a vape shop", 120, 2, lease=lease["DL-0512"],
             how_received=Case.Received.LETTER)
    c.acknowledged_on, c.application_complete_on = c.received_on + timedelta(days=3), c.received_on + timedelta(days=9)
    c.decision, c.decision_on = Case.Decision.REFUSED, c.received_on + timedelta(days=30)
    c.reasons = "The proposed use conflicts with the council's estate management policy for the precinct's mix."
    c.stage, c.status, c.closed_on = "decision", Case.Status.CLOSED, c.received_on + timedelta(days=36)
    c.outcome = "Tenant told in writing; no appeal."
    c.refresh_target()
    c.save()
    declare(c)
    # 3. Alterations to the pharmacy: being assessed, waiting for the supervisor.
    c = case("alterations", "Consultation room and new shop front, 1 The Precinct", 26, 3, lease=lease["DL-0511"],
             how_received=Case.Received.ONLINE)
    c.acknowledged_on, c.application_complete_on = c.received_on + timedelta(days=2), c.received_on + timedelta(days=8)
    c.stage = "assessing"
    c.refresh_target()
    c.save()
    tick(c, "Acknowledge", "Drawings")
    declare(c)
    if head and c.owner_id and c.owner_id != head.pk:
        Approval.objects.create(case=c, stage="decision", requested_by=c.owner, approver=head, status="pending",
                                recommendation="Grant a licence for alterations with reinstatement on request and "
                                               "planning consent for the shop front.")
    # 4. Dilapidations on the ended lease of Unit 4.
    c = case("dilapidations", "Dilapidations claim, Unit 4 Northfield Business Park", 50, 4, lease=lease["DL-0504"],
             property=P["DM-N01-U04"], how_received=Case.Received.LETTER)
    c.stage = "assessing"
    c.dilaps_schedule_value, c.dilaps_served_on = D("68500"), today - timedelta(days=40)
    c.dilaps_response_value, c.dilaps_response_on = D("31000"), today - timedelta(days=6)
    c.dilaps_notes = "Section 18(1) valuation commissioned: the unit will be refurbished before reletting."
    c.save()
    if legal:
        c.contributors.add(legal)
    # 5. A request to buy a strip of the former bus depot.
    c = case("land_purchase", "Request to buy a strip of the former bus depot for garden land", 70, 5,
             property=P["DM-N06"], how_received=Case.Received.EMAIL)
    c.acknowledged_on, c.stage = c.received_on + timedelta(days=6), "gathering"
    c.save()
    CaseNote.objects.create(case=c, text="Neighbour at 14 Depot Road. Check whether a sale would prejudice the wider "
                                         "disposal and whether the strip is in the contaminated area.")
    # 6. A wayleave request for a new fibre cable.
    c = case("wayleave", "Wayleave for a fibre cable across the business park verge", 18, 6,
             property=P["DM-N01-L01"],
             party=Party.objects.filter(name="Example Mobile Networks Ltd").first(), how_received=Case.Received.EMAIL)
    c.acknowledged_on, c.stage = c.received_on + timedelta(days=1), "gathering"
    c.save()
    # 7. A breach of the user clause at the market hall: past target.
    c = case("breach", "Market hall used for late-night events without consent", 75, 7, lease=lease["DL-0524"],
             how_received=Case.Received.PHONE)
    c.stage, c.target_date = "assessing", today - timedelta(days=12)
    c.save()
    CaseNote.objects.create(case=c, text="Residents' complaints logged with environmental health. Warning letter "
                                         "drafted; waiting for the operator's licence details.")
    # 8. A service charge query on the business park.
    c = case("sc_dispute", "Query about the 2025/26 security patrol costs", 14, 8, lease=lease["DL-0502"],
             how_received=Case.Received.EMAIL)
    c.acknowledged_on = c.received_on + timedelta(days=2)
    c.save()
    # 9. A new letting of Studio 2: heads of terms nearly complete, conflict declared.
    c = case("new_letting", "New licence of Studio 2, Innovation Hub", 22, 9, property=P["DM-N12-U02"],
             how_received=Case.Received.ONLINE)
    c.acknowledged_on, c.stage, c.tenant_represented = c.received_on + timedelta(days=2), "assessing", "yes"
    c.heads_of_terms = {"premises": "Studio 2 as shown on the plan", "term": "12-month licence, renewable",
                        "rent": "£7,200 a year, monthly in advance, including service costs", "vat": "VAT charged",
                        "security": "One month's licence fee", "repairs": "Licensor repairs; licensee keeps tidy",
                        "service_insurance": "Included in the licence fee"}
    c.save()
    declare(c, "The applicant's director is a former council employee who worked in the estates team. "
               "Lena Chen negotiates; Rob Baker checks the terms.")
    # 10. Renewal opposed on redevelopment grounds.
    c = case("renewal", "Renewal of Unit 7: opposed on ground (f)", 60, 10, lease=lease["DL-0507"],
             how_received=Case.Received.LETTER)
    c.stage, c.notice_kind, c.notice_served_on = "assessing", "s25", today - timedelta(days=60)
    c.notice_date, c.landlord_opposes = today + timedelta(days=150), True
    c.opposition_grounds = "Section 30(1)(f): demolition and reconstruction of the workshop block"
    c.tenant_represented = "yes"
    from apps.cases.leasing import notice_dates

    c.target_date = notice_dates(c).court_deadline
    c.save()
    return made


def load_maintenance(today):
    from apps.core.dates import add_months
    from apps.maintenance import library, workflow
    from apps.maintenance.models import Component, Contract, Contractor, Job, PlannedTask, Responsibility

    from .models import Property

    if Contractor.objects.filter(finance_supplier_ref="DEMO-GROUNDS").exists():
        return 0
    P = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-N")}
    c = {x.finance_supplier_ref.split("-", 1)[1].lower(): x
         for x in Contractor.objects.filter(finance_supplier_ref__startswith="DEMO-")}
    for key, name, trades, days in [("grounds", "Northfield Grounds and Drainage Ltd", "Grounds, drains, gullies", 120),
                                    ("glazing", "Clearview Glazing Northfield", "Glazing, shop fronts, shutters", 12)]:
        c[key] = Contractor.objects.create(
            name=name, trades=trades, contact_name="Service desk", email=f"{key}@example.org", phone="01632 960050",
            emergency_phone="01632 960051", insurer="Example Mutual Insurance", public_liability=D("5000000"),
            insurance_expires=today + timedelta(days=days), finance_supplier_ref=f"DEMO-{key.upper()}",
            notes="Fictional demonstration contractor.")
    plant = Contract.objects.create(contractor=c["heating"], title="Leisure centre and library plant maintenance",
                                    reference="NTH/MECH/24", starts=add_months(today, -20),
                                    ends=add_months(today, 4), annual_value=D("31500"))
    plant.properties.add(P["DM-N03"], P["DM-N04"])
    grounds = Contract.objects.create(contractor=c["grounds"], title="Business park grounds and gully cleaning",
                                      reference="NTH/GRND/25", starts=add_months(today, -8),
                                      ends=add_months(today, 28), annual_value=D("9600"), service_charge=True)
    grounds.properties.add(P["DM-N01"])

    comp = {}
    for ref, name, cat, loc, installed, life, cond, cost in [
            ("DM-N04", "Pool filtration and dosing plant", "mechanical", "Pool plant room", 2006, 20, "C", 240000),
            ("DM-N04", "Main hall roof (profiled metal)", "roof", "Sports hall", 1998, 30, "C", 310000),
            ("DM-N04", "Air handling units (3)", "mechanical", "Roof plant deck", 2011, 20, "B", 180000),
            ("DM-N03", "Flat roof (asphalt)", "roof", "Whole building", 1987, 25, "D", 95000),
            ("DM-N03", "Electrical distribution", "electrical", "Whole building", 1999, 30, "B", 70000),
            ("DM-N03", "Passenger lift", "lift", "Stair core", 2008, 25, "B", 65000),
            ("DM-N01-B01", "Roller shutter doors (5)", "external", "Loading bays", 2008, 20, "C", 45000),
            ("DM-N09", "Glazed roof lantern", "roof", "Market floor", 1890, 40, "C", 220000),
            ("DM-N02-B01", "Shop front shutters", "external", "Ground floor", 2014, 15, "B", 36000)]:
        comp[name] = Component.objects.create(
            property=P[ref], name=name, category=cat, location=loc, installed_year=installed, life_years=life,
            condition=cond, condition_on=today - timedelta(days=150), replacement_cost=D(cost), capital=True)

    for ref, code, due, contractor, contract in [
            ("DM-N04", "legionella_ra", 35, "heating", plant), ("DM-N04", "water_temps", -3, "heating", plant),
            ("DM-N04", "fire_alarm", 50, "electrical", None), ("DM-N04", "boiler_service", 80, "heating", plant),
            ("DM-N04", "aircon_tm44", 600, "heating", None), ("DM-N03", "lift_exam", 12, "heating", plant),
            ("DM-N03", "lift_service", 40, "heating", plant), ("DM-N03", "emergency_lighting", -20, "electrical", None),
            ("DM-N03", "asbestos", 75, None, None), ("DM-N09", "fire_doors", 30, "building", None),
            ("DM-N01-L01", "drains", 55, "grounds", grounds), ("DM-N01-B01", "roof_gutters", 95, "roofing", None),
            ("DM-N02-B01", "eicr", 300, "electrical", None)]:
        _code, title, category, months, statutory, regulation = library.BY_CODE[code]
        next_due = today + timedelta(days=due)
        PlannedTask.objects.create(
            property=P[ref], title=title, category=category, frequency_months=months, statutory=statutory,
            regulation=regulation, contractor=c.get(contractor), contract=contract, next_due=next_due,
            last_done=add_months(next_due, -months), estimated_cost=D("420") if months <= 12 else D("1600"))
    workflow.auto_raise(today)

    head = get_user_model().objects.filter(username="demo.head").first()

    def job(ref, title, **fields):
        return workflow.open_job(P[ref], title, **fields)

    j = job("DM-N04", "Pool hall ceiling tile fallen near the learner pool", category="internal",
            priority="emergency", reported_on=today - timedelta(days=1), how_reported="phone",
            reported_by="Duty manager, Northfield Leisure Trust", contractor=c["building"], estimate=D("900"),
            description="Learner pool closed. Check the remaining tiles and the ceiling grid for corrosion.")
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=1))
    job("DM-N03", "Damp patch spreading on the children's library ceiling", category="roof", priority="urgent",
        reported_on=today - timedelta(days=12), how_reported="email", reported_by="Library manager",
        component=comp["Flat roof (asphalt)"], contractor=c["roofing"], estimate=D("2400"))
    j = job("DM-N01-U02", "Roller shutter will not close fully", category="external", priority="urgent",
            reported_on=today - timedelta(days=16), how_reported="tenant", reported_by="Northfield Packaging Ltd",
            component=comp["Roller shutter doors (5)"], contractor=c["building"], estimate=D("780"))
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=15))
    j = job("DM-N02-U06", "Shop front window cracked by a shopping trolley", category="external",
            priority="routine", reported_on=today - timedelta(days=45), how_reported="tenant",
            contractor=c["glazing"], estimate=D("560"), responsibility=Responsibility.TENANT,
            responsibility_reason="Internal repairing lease: the tenant repairs the shop front glass")
    j = job("DM-N01-L01", "Blocked gully flooding the estate road", category="ext_works", priority="urgent",
            reported_on=today - timedelta(days=28), how_reported="inspection", contractor=c["grounds"],
            estimate=D("350"))
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=28))
    workflow.complete(j, today - timedelta(days=25), D("395"), "Gully jetted and silt trap cleared.", "NGD-2210")
    j = job("DM-N09", "Replace cracked panes in the roof lantern", category="roof", priority="planned",
            reported_on=today - timedelta(days=8), how_reported="inspection", contractor=c["glazing"],
            estimate=D("14800"), component=comp["Glazed roof lantern"],
            description="Twelve cracked panes found at the condition survey. Listed building consent may be needed.")
    if head and j.owner and j.owner != head:
        j.approval_status, j.approver = "pending", head
        j.save()
    j = job("DM-N01-U06", "Graffiti on the workshop roller shutter", category="external", priority="routine",
            reported_on=today - timedelta(days=60), how_reported="inspection", contractor=c["building"],
            estimate=D("180"), responsibility=Responsibility.RECHARGE,
            responsibility_reason="Tenant's covenant to keep the shutter clean: recharge")
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=58))
    workflow.complete(j, today - timedelta(days=50), D("180"), "Graffiti removed and shutter resprayed.", "RBM-4520")
    j = job("DM-N04", "Main pool circulation pump failure", category="mechanical", priority="emergency",
            reported_on=today - timedelta(days=90), how_reported="phone", contractor=c["heating"],
            estimate=D("3200"), component=comp["Pool filtration and dosing plant"])
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=90))
    workflow.complete(j, today - timedelta(days=88), D("3460"), "Pump replaced; pool reopened after water tests.",
                      "HWM-1302")
    j.status = Job.Status.CLOSED
    j.save()
    job("DM-N05", "Hall heating not reaching temperature", category="mechanical", priority="routine",
        reported_on=today - timedelta(days=4), how_reported="email", reported_by="Hall bookings secretary")
    return Job.objects.filter(property__reference__startswith="DM-N").count()


def load_compliance(today):
    from django.core.files.base import ContentFile

    from apps.compliance import workflow
    from apps.compliance.models import Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType

    from .demo_media import placeholder_pdf
    from .models import Property

    P = {p.reference: p for p in Property.objects.filter(reference__startswith="DM-N")}
    if not P or BuildingSafety.objects.filter(property__in=P.values()).exists():
        return 0
    kinds = {k.code: k for k in ComplianceType.objects.all()}
    plan = {
        "DM-N04": ["fra", "fire_alarm", "emergency_lighting", "gas", "eicr", "legionella", "asbestos", "pressure",
                   "tm44", "dec"],
        "DM-N03": ["fra", "fire_alarm", "emergency_lighting", "eicr", "asbestos", "lift", "dec"],
        "DM-N09": ["fra", "eicr", "asbestos", "epc"],
        "DM-N02-B01": ["fra", "eicr", "asbestos"],
        "DM-N05": ["fra", "gas", "eicr", "epc"],
        "DM-N01-U04": ["epc"], "DM-N01-U10": ["epc"], "DM-N02-U03": ["epc"], "DM-N02-U07": ["epc"],
        "DM-N12-U02": ["epc"],
    }
    reqs = {}
    for ref, codes in plan.items():
        for req in workflow.add_requirements(P[ref], [kinds[c] for c in codes]):
            reqs[(ref, req.kind.code)] = req

    def cert(ref, code, months_ago, result="ok", rating="", actions=(), by="Fictional inspector"):
        from apps.core.dates import add_months

        req = reqs[(ref, code)]
        c = Certificate(requirement=req, issued_on=add_months(today, -months_ago), result=result, rating=rating,
                        carried_out_by=by, reference=f"DEMO-{code.upper()}-{req.pk}")
        c.file.save(f"{code}.pdf", ContentFile(placeholder_pdf(f"{req.kind.name}, {req.property.name}",
                                                               ["A fictional document for demonstrating PHAEMA."],
                                                               banner="FICTIONAL DEMONSTRATION DOCUMENT")), save=False)
        c.original_filename = f"{code}.pdf"
        c.save()
        for text, priority, done in actions:
            Action.objects.create(certificate=c, description=text, priority=priority,
                                  done_on=c.issued_on + timedelta(days=20) if done else None)
        return c

    cert("DM-N04", "fra", 4, "actions", actions=[
        ("Clear stored equipment from the escape route behind the sports hall", "high", False),
        ("Repair the self-closer on the plant room door", "medium", True)], by="Northfield Leisure Trust")
    cert("DM-N04", "fire_alarm", 3)
    cert("DM-N04", "emergency_lighting", 13)            # expired
    cert("DM-N04", "gas", 8)
    cert("DM-N04", "eicr", 40, "actions", actions=[("Replace corroded pool hall light fittings (C2)", "medium", False)])
    cert("DM-N04", "legionella", 10)                     # expires soon
    cert("DM-N04", "asbestos", 6)
    cert("DM-N04", "pressure", 7)
    cert("DM-N04", "dec", 5, rating="D")
    # DM-N04 TM44 air conditioning inspection: missing
    cert("DM-N03", "fra", 14)                            # expired
    cert("DM-N03", "fire_alarm", 5)
    cert("DM-N03", "emergency_lighting", 2)
    cert("DM-N03", "eicr", 55, "fail")                   # unsatisfactory and out of date
    cert("DM-N03", "asbestos", 9, "actions", actions=[("Label the AIB ceiling panels in the first floor void", "high",
                                                       False)])
    cert("DM-N03", "lift", 5)
    cert("DM-N03", "dec", 8, rating="F")
    cert("DM-N09", "fra", 2)
    cert("DM-N09", "eicr", 18)
    cert("DM-N09", "epc", 30, rating="E")
    # DM-N09 asbestos: missing
    cert("DM-N02-B01", "fra", 11)
    cert("DM-N02-B01", "eicr", 44)
    cert("DM-N02-B01", "asbestos", 20)
    cert("DM-N05", "fra", 7, by="Northfield Community Association")
    cert("DM-N05", "gas", 12, by="Northfield Community Association")  # expires about now
    cert("DM-N05", "eicr", 22)
    cert("DM-N05", "epc", 70, rating="D")
    cert("DM-N01-U04", "epc", 100, rating="G")           # expired and below the letting minimum
    cert("DM-N01-U10", "epc", 15, rating="B")
    cert("DM-N02-U03", "epc", 50, rating="C")
    cert("DM-N02-U07", "epc", 80, rating="F")            # below the letting minimum
    # DM-N12-U02 EPC: missing, with a new letting case open

    for ref, height, storeys, homes, tier, rp in [
            ("DM-N04", "11.0", 2, 0, "B", "Northfield Leisure Trust (day to day); council (structure)"),
            ("DM-N03", "8.5", 2, 0, "B", "Exampleton Council, Facilities"),
            ("DM-N02-B01", "10.5", 3, 0, "B", "Exampleton Council, Estates"),
            ("DM-N09", "14.0", 2, 0, "B", "Northfield Markets Ltd"),
            ("DM-N06", None, None, 0, "C", "")]:
        BuildingSafety.objects.create(property=P[ref], height_m=height, storeys=storeys, residential_units=homes,
                                      tier=tier, confirmed_on=today - timedelta(days=45),
                                      confirmed_by=P[ref].managing_surveyor, responsible_person=rp)
    for ref, category, title, year in [
            ("DM-N03", "asbestos", "Asbestos register and management plan", 2024),
            ("DM-N03", "plans", "Library floor plans", 1987),
            ("DM-N04", "om", "Pool plant operation and maintenance manual", 2006),
            ("DM-N04", "fire", "Fire strategy drawings", 2011),
            ("DM-N04", "risk", "Pool safety operating procedure (normal and emergency action plans)", 2025),
            ("DM-N09", "survey", "Condition survey of the market hall", 2026),
            ("DM-N06", "survey", "Phase 2 ground investigation report", 2025)]:
        d = BuildingDocument(property=P[ref], category=category, title=title, document_date=date(year, 5, 1),
                             original_filename=f"{category}.pdf")
        d.file.save(f"{category}.pdf", ContentFile(placeholder_pdf(title, ["A fictional document for demonstrating "
                                                                           "PHAEMA."],
                                                                   banner="FICTIONAL DEMONSTRATION DOCUMENT")),
                    save=False)
        d.save()
    return len(reqs)


def load_valuations(today):
    """Give Northfield assets to the two new surveyors and raise one open audit query."""
    from apps.valuations import workflow
    from apps.valuations.models import Valuation, ValuationSettings

    year_end = ValuationSettings.load().year_end(today)
    users = {u.username: u for u in get_user_model().objects.filter(username__in=("demo.lchen", "demo.head"))}
    if "demo.lchen" in users:
        mine = workflow.staff_valuer(users["demo.lchen"])
        for ref in ("DM-N07", "DM-N10"):  # in this year's programme; Lena Chen manages both
            v = Valuation.objects.filter(property__reference=ref, valuation_date=year_end).first()
            if v and v.valuer_id != mine.pk:
                workflow.assign(v, mine)
    last = Valuation.objects.filter(property__reference="DM-N09", valuation_date__lt=year_end,
                                    status="accepted").order_by("-valuation_date").first()
    if last and "demo.head" in users and not last.audit_reviews.exists():
        workflow.flag(last, users["demo.head"], "Please explain the turnover rent assumption and the yield applied "
                      "to the market hall.", "query", "Example Audit LLP (fictional)", today + timedelta(days=21))
