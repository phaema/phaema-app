# SPDX-License-Identifier: AGPL-3.0-or-later
"""Three more fictional districts, Northfield, Westbrook and Kingsmere, which with Exampleton make up the
demonstration data.

The three districts share one layout (a business park, a shopping precinct, a library, a leisure centre and so on),
each with its own town name, references, map position, rents and dates, so the data is about four times what one
district gives. Northfield is the district the e-learning, the tour and the tests name, and its records are
exactly as they always were.

Like Exampleton, everything is invented: ZZ9x pseudo-postcodes, 9999… UPRNs, ZZ title numbers, ZZ company numbers,
example.org emails and Ofcom's drama telephone range. References keep the DM- (property), DL- (agreement) and DEMO
(cases, contractors, valuers) prefixes, so `load_demo_data --reset` removes every district with the rest.

Each function is called by load_demo_data at the point where the matching Exampleton data is loaded, once for each
district.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


@dataclass(frozen=True)
class District:
    n: int  # 1, 2, 3: sets the agreement, title, company, telephone and finance number ranges
    code: str  # property references DM-<code>01…, cases DEMO-<code>1…
    town: str
    abbr: str  # contract references
    dx: int  # where the district sits on the map, in metres from Exampleton
    dy: int
    postcode: str
    farm: str  # name of the county farm
    farmers: str
    surveyors: dict = field(default_factory=dict)  # username: (first name, last name); the first leads
    shift: int = 0  # months added to every agreement's start, so events fall at different times
    rent_factor: D = D("1")

    @property
    def prefix(self):
        return f"DM-{self.code}"

    @property
    def lease_prefix(self):
        return f"DL-0{self.n + 4}"

    def lease(self, k):
        return f"DL-{400 + 100 * self.n + k:04d}"

    @property
    def crm(self):
        return f"DEMO-{self.code}"

    @property
    def lead(self):
        return next(iter(self.surveyors))

    @property
    def second(self):
        return list(self.surveyors)[1]

    def rent(self, amount):
        """A rent adjusted for the district, to the nearest £50."""
        value = D(amount) * self.rent_factor
        return (value / 50).quantize(D("1"), rounding=ROUND_HALF_UP) * 50 if value else D(amount)


NORTH = District(1, "N", "Northfield", "NTH", 2600, 1700, "ZZ98", "Hilltop", "Beth and Dan Hill",
                 {"demo.lchen": ("Lena", "Chen"), "demo.rbaker": ("Rob", "Baker")})
WEST = District(2, "W", "Westbrook", "WBK", -4300, -500, "ZZ97", "Brookside", "Sam and Jo Brook",
                {"demo.fkhan": ("Farah", "Khan"), "demo.tevans": ("Tom", "Evans")}, shift=-3, rent_factor=D("0.9"))
KINGS = District(3, "K", "Kingsmere", "KGM", 1500, -3400, "ZZ96", "Mereside", "Ann and Lee Marsh",
                 {"demo.mokafor": ("Mia", "Okafor"), "demo.jreid": ("James", "Reid")}, shift=2,
                 rent_factor=D("1.12"))
DISTRICTS = (NORTH, WEST, KINGS)

TOWN = NORTH.town
DX, DY = NORTH.dx, NORTH.dy


def assignments(d):
    p, lead, second = d.prefix, d.lead, d.second
    return {
        f"{p}01": lead, f"{p}07": lead, f"{p}10": lead, f"{p}12": lead,
        f"{p}02": second, f"{p}05": second, f"{p}08": second, f"{p}09": second,
        f"{p}03": "demo.ojones", f"{p}04": "demo.ojones", f"{p}11": "demo.ojones",
        # <code>06 is left unassigned, like DM-S06 and DM-S10.
    }


def portfolios(d):
    p = d.prefix
    return {
        f"{p}01": "Investment", f"{p}01-L01": "Highways and transport", f"{p}02": "Investment",
        f"{p}03": "Libraries", f"{p}04": "Leisure", f"{p}05": "Community",
        f"{p}06": "Regeneration and development", f"{p}07": "Investment", f"{p}08": "Parks and open spaces",
        f"{p}09": "Markets", f"{p}10": "Farms and rural estate", f"{p}11": "Highways and transport",
        f"{p}12": "Economic development",
    }


def add_records(add, rect):
    """Add every district's properties to the demo property list."""
    for d in DISTRICTS:
        add_district(d, add, rect)


def add_district(d, add, rect):
    """Add one district's properties, parents before children."""
    from .management.commands.load_demo_data import uprn

    p, town, pc = d.prefix, d.town, d.postcode
    usrn = f"999{9 - d.n}000"

    def r(dx, dy, w, h):
        return rect(d.dx + dx, d.dy + dy, w, h)

    def put(ref, name, ptype, parent=None, **fields):
        fields.setdefault("town", town)
        add(ref, name, ptype, parent, **fields)

    # 1. The business park: estate > two blocks > ten units, and the estate roads
    put(f"{p}01", f"{town} Business Park", "estate", holding_purpose="investment", tenure="freehold",
        occupation="part_let", use_description="Business park", address_line_1="Enterprise Road",
        postcode=f"{pc} 1BP", usrn=f"{usrn}1", boundary=r(0, 0, 380, 220),
        notes="Business park built by the council in 2008, let on a mix of protected and contracted-out leases.",
        location_description=f"On the eastern edge of {town}, about a mile from the town centre and half a mile "
                             "from the ring road. Reached from Enterprise Road, with housing to the west and "
                             "farmland to the east.",
        building_description="Two terraces of industrial units around a shared service yard: the Hangar block of "
                             "five warehouse units and the Workshop block of five smaller workshops, with estate "
                             "roads, verges and car parking.",
        built="2008", site_area_ha=D("8.36"), parking="Marked spaces in front of each unit and a shared visitor "
                                                      "car park by the entrance.", parking_spaces=96,
        mains_gas="yes", electricity="three", mains_water="yes", drainage="mains")
    blocks = {"B01": ("Hangar block", 20, 20, [("01", "let", 650), ("02", "let", 650), ("03", "let", 650),
                                               ("04", "vacant", 650), ("05", "let", 1300)]),
              "B02": ("Workshop block", 20, 130, [("06", "let", 240), ("07", "let", 240), ("08", "let", 240),
                                                  ("09", "let", 240), ("10", "vacant", 480)])}
    for bref, (bname, bx, by, units) in blocks.items():
        block = f"{p}01-{bref}"
        put(block, bname, "building", f"{p}01", holding_purpose="investment", tenure="freehold",
            occupation="part_let", use_description="Industrial and warehouse", use_class="B8",
            address_line_1=f"{bname}, Enterprise Road", postcode=f"{pc} 1BP",
            gia_sqm=D(sum(u[2] for u in units)) * D("1.08"), boundary=r(bx, by, 68 * len(units), 70),
            building_description=f"Terrace of {len(units)} single-storey units, each with a roller shutter door, "
                                 "personnel door and a small office and WC.",
            built="2008", construction_type="portal_frame",
            construction_detail="Blockwork to 2 m with profiled metal cladding above, "
                                "power-floated concrete floor.",
            storeys=1, roof_type="pitched", roof_covering="composite",
            roof_detail="Shallow pitch with about 10% roof lights.", window_type="aluminium",
            mains_gas="yes", electricity="three", mains_water="yes", drainage="mains",
            solar_pv="yes" if bref == "B01" else "no", solar_capacity_kwp=D("150") if bref == "B01" else None)
        for i, (num, occ, nia) in enumerate(units):
            put(f"{p}01-U{num}", f"Unit {int(num)}, {town} Business Park", "unit", block, uprn=uprn(),
                holding_purpose="investment", tenure="freehold", occupation=occ,
                use_description="Warehouse" if nia >= 600 else "Workshop",
                use_class="B8" if nia >= 600 else "E(g)(iii)", address_line_1=f"Unit {int(num)}, Enterprise Road",
                postcode=f"{pc} 1BP", nia_sqm=D(nia), gia_sqm=D(nia) * D("1.05"), boundary=r(bx + 68 * i, by, 68, 70))
    put(f"{p}01-L01", "Business park roads and verges", "land", f"{p}01", holding_purpose="operational",
        tenure="freehold", occupation="na", use_description="Estate roads", boundary=r(0, 95, 380, 30),
        site_hazards="HGV movements all day. Wear high-visibility clothing and keep to the footpath.")

    # 2. The Precinct: eight shops with offices over
    put(f"{p}02", f"{town} Precinct", "site", holding_purpose="investment", tenure="freehold",
        occupation="part_let", use_description="Shopping precinct", address_line_1="The Precinct",
        postcode=f"{pc} 2PR", usrn=f"{usrn}2", boundary=r(500, 300, 170, 50))
    put(f"{p}02-B01", "1–8 The Precinct", "building", f"{p}02", uprn=uprn(), holding_purpose="investment",
        tenure="freehold", occupation="part_let", use_description="Shops with offices over",
        address_line_1="1–8 The Precinct", postcode=f"{pc} 2PR", gia_sqm=D("1620"), boundary=r(500, 300, 170, 30))
    shops = [("Pharmacy", "let", 110), ("Shop", "let", 80), ("Shop", "vacant", 80), ("Bakery", "let", 95),
             ("Shop", "let", 80), ("Café", "let", 105), ("Shop", "vacant", 80), ("Launderette", "let", 90)]
    classes = {"Shop": "E(a)", "Pharmacy": "E(a)", "Bakery": "E(a)", "Café": "E(b)", "Launderette": "E(c)"}
    for i, (use, occ, nia) in enumerate(shops, start=1):
        put(f"{p}02-U0{i}", f"{i} The Precinct", "unit", f"{p}02-B01", uprn=uprn(), holding_purpose="investment",
            tenure="freehold", occupation=occ, use_description=use, use_class=classes[use],
            address_line_1=f"{i} The Precinct", postcode=f"{pc} 2PR", nia_sqm=D(nia), gia_sqm=D(nia) * D("1.1"),
            boundary=r(500 + 21 * (i - 1), 300, 21, 30))
    put(f"{p}02-U09", "Upper floors, 1–8 The Precinct", "unit", f"{p}02-B01", uprn=uprn(),
        holding_purpose="investment", tenure="freehold", occupation="let", use_description="Offices",
        use_class="E(g)(i)", address_line_1="Upper floors, The Precinct", postcode=f"{pc} 2PR", nia_sqm=D("520"))

    # 3. Operational, community, surplus and other land
    put(f"{p}03", f"{town} Library", "building", uprn=uprn(), holding_purpose="operational", tenure="freehold",
        occupation="council", use_description="Public library", use_class="F1(d)", address_line_1="Library Square",
        postcode=f"{pc} 3LS", gia_sqm=D("1180"), boundary=r(420, 420, 45, 35),
        site_hazards="Asbestos insulating board in the first floor ceiling void: do not disturb. Check the register.",
        notes="1960s library with a community meeting room. Listed as an asset of community value (fictional).",
        location_description="In the town centre on the north side of Library Square, next to the bus station.",
        building_description="Purpose-built two-storey public library with a community meeting room and staff "
                             "offices on the first floor.",
        built="1964", construction_type="concrete_frame", construction_detail="Concrete frame with brick infill.",
        storeys=2, roof_type="flat", roof_covering="asphalt", roof_detail="Mastic asphalt on a concrete deck, "
                                                                           "last overlaid in 1987.",
        window_type="aluminium", window_detail="Replaced in 2011.", parking="None on site; public car park "
                                                                            "opposite.", parking_spaces=0,
        mains_gas="yes", electricity="three", mains_water="yes", drainage="mains", solar_pv="no")
    put(f"{p}04", f"{town} Leisure Centre", "building", uprn=uprn(), holding_purpose="community",
        tenure="freehold", occupation="let", use_description="Leisure centre with pool", use_class="F2(c)",
        address_line_1="Park Road", postcode=f"{pc} 3PR", gia_sqm=D("5400"), boundary=r(700, 420, 110, 70),
        site_hazards="Pool plant room: chemical store and confined space. Visits by arrangement with the duty manager.",
        notes=f"Run by {town} Leisure Trust on a 30-year lease at a peppercorn, with an annual management fee.")
    put(f"{p}05", f"{town} Community Hall", "building", uprn=uprn(), holding_purpose="community",
        tenure="freehold", occupation="let", use_description="Community hall", use_class="F2(b)",
        address_line_1="Church Lane", postcode=f"{pc} 4CL", gia_sqm=D("410"), boundary=r(300, 600, 35, 25))
    put(f"{p}06", f"Former {town} bus depot", "land", holding_purpose="surplus", tenure="freehold",
        occupation="vacant", use_description="Cleared brownfield site", address_line_1="Depot Road",
        postcode=f"{pc} 5DR", boundary=r(-300, 300, 160, 120),
        site_hazards="Unsecured excavations and possible ground contamination. Do not enter without the site key holder.",
        notes="Declared surplus. Ground investigation found hydrocarbons near the former fuel tanks.")
    put(f"{p}07", "Water tower telecoms site", "land", holding_purpose="investment", tenure="freehold",
        occupation="let", use_description="Telecommunications mast", address_line_1="Tower Hill",
        postcode=f"{pc} 6TH", boundary=r(-100, 600, 20, 20),
        notes="Code agreement under the Electronic Communications Code (fictional operator).")
    put(f"{p}08", f"{town} Park pavilion and pitches", "land", holding_purpose="community", tenure="freehold",
        occupation="let", use_description="Sports pitches and changing pavilion", address_line_1="Park Road",
        postcode=f"{pc} 3PR", boundary=r(820, 420, 200, 140))
    put(f"{p}09", f"{town} Market Hall", "building", uprn=uprn(), holding_purpose="investment",
        tenure="freehold", occupation="let", use_description="Covered market", use_class="Sui generis",
        address_line_1="Market Street", postcode=f"{pc} 2MS", gia_sqm=D("2100"), boundary=r(560, 380, 60, 35),
        notes="Victorian market hall, Grade II listed. Let to a market operator who licenses the stalls.")
    put(f"{p}10", f"{d.farm} Farm", "land", holding_purpose="investment", tenure="freehold", occupation="let",
        use_description="Mixed farm (72 hectares)", address_line_1=f"{d.farm} Lane", postcode=f"{pc} 7HL",
        boundary=r(-1100, 900, 700, 500), notes="County farms estate holding, let on a farm business tenancy.")
    put(f"{p}11", "Kingsway car park", "site", uprn=uprn(), holding_purpose="operational", tenure="freehold",
        occupation="council", use_description="Surface car park (180 spaces)", address_line_1="Kingsway",
        postcode=f"{pc} 2KW", boundary=r(680, 300, 80, 50))
    put(f"{p}12", f"{town} Innovation Hub", "building", uprn=uprn(), holding_purpose="investment",
        tenure="leasehold", occupation="part_let", use_description="Start-up offices", use_class="E(g)(i)",
        address_line_1="Station Approach", postcode=f"{pc} 8SA", gia_sqm=D("640"), boundary=r(380, 520, 30, 25),
        notes="Leased in by the council from a private landlord for ten years, sub-let to new businesses.")
    for i, (occ, nia) in enumerate([("let", 85), ("vacant", 85)], start=1):
        put(f"{p}12-U0{i}", f"Studio {i}, Innovation Hub", "unit", f"{p}12", uprn=uprn(),
            holding_purpose="investment", tenure="leasehold", occupation=occ, use_description="Office studio",
            use_class="E(g)(i)", address_line_1=f"Studio {i}, Station Approach", postcode=f"{pc} 8SA",
            nia_sqm=D(nia))


def titles(d):
    p, t = d.prefix, 10 * d.n
    packet = 300 + 100 * (d.n - 1)
    return [
        {"title_number": f"ZZ1000{t + 1}", "tenure": "freehold", "title_class": "absolute",
         "deeds_location": "Digital copy only", "refs": [f"{p}01"],
         "restrictions_and_covenants": "Covenant to maintain a landscaped buffer along the northern boundary."},
        {"title_number": f"ZZ1000{t + 2}", "tenure": "freehold", "title_class": "absolute",
         "deeds_location": f"Legal Services strongroom, packet {packet + 1}", "refs": [f"{p}02", f"{p}09", f"{p}11"]},
        {"title_number": f"ZZ1000{t + 3}", "tenure": "freehold", "title_class": "absolute",
         "deeds_location": f"Legal Services strongroom, packet {packet + 2}", "refs": [f"{p}03", f"{p}04", f"{p}08"],
         "restrictions_and_covenants": "Park land held for public recreation: disposal needs advertising under "
                                       "s123(2A)."},
        {"title_number": None, "tenure": "freehold", "title_class": "unregistered",
         "deeds_location": f"Legal Services strongroom, packet {44 + d.n - 1} (conveyance 1931)", "refs": [f"{p}05"]},
        {"title_number": f"ZZ1000{t + 4}", "tenure": "freehold", "title_class": "qualified",
         "deeds_location": "Digital copy only", "refs": [f"{p}06"],
         "restrictions_and_covenants": "Qualified title: the 1952 conveyance is missing. Title insurance on disposal."},
        {"title_number": f"ZZ1000{t + 5}", "tenure": "freehold", "title_class": "absolute",
         "deeds_location": "County farms archive", "refs": [f"{p}07", f"{p}10"]},
        {"title_number": f"ZZ2000{t + 1}", "tenure": "leasehold", "title_class": "absolute",
         "deeds_location": f"Legal Services strongroom, packet {packet + 30}", "refs": [f"{p}12"],
         "restrictions_and_covenants": "10-year lease; tenant's break at year 5 on six months' notice."},
    ]


def photos(d):
    p, town = d.prefix, d.town
    return {
        f"{p}01": [(f"{town} Business Park entrance", "industrial")],
        f"{p}01-U04": [("Unit 4 front elevation", "industrial"), ("Unit 4 interior", "industrial")],
        f"{p}02-B01": [("The Precinct from the square", "retail"), ("Shop fronts, north side", "retail")],
        f"{p}03": [(f"{town} Library entrance", "civic")],
        f"{p}06": [("Former bus depot from Depot Road", "land"), ("Former fuel tank area", "land")],
    }


def parties(d):
    town = d.town
    return [
        (f"{town} Freight Ltd", "company", "Hannah Ward"),
        (f"{town} Packaging Ltd", "company", "Imran Ali"),
        (f"{town} Self Storage Ltd", "company", "Operations Manager"),
        (f"{town} Group plc", "company", "Company Secretary"),
        (f"{town} Brewing Co Ltd", "company", "Sophie Turner"),
        (f"{town} Joinery Workshop", "sole_trader", "Mark Davies"),
        (f"{town} Bikes", "partnership", "Ana and Tom Field"),
        (f"{town} Ceramics Ltd", "company", "Ellie Moss"),
        (f"{town} Pharmacy Ltd", "company", "Raj Mehta"),
        (f"{town} News and Post", "sole_trader", "Gary Hunt"),
        (f"{town} Bakery", "partnership", "Ruth and Ian Baker"),
        (f"{town} Phone Repairs", "sole_trader", "Kai Wong"),
        (f"{town} Coffee House Ltd", "company", "Lucy Price"),
        (f"{town} Launderette", "sole_trader", "Olu Adeyemi"),
        (f"{town} Training Services Ltd", "company", "Centre Manager"),
        (f"{town} Leisure Trust", "charity", "Chief Executive"),
        (f"{town} Community Association", "charity", "Hall Bookings Secretary"),
        ("Example Mobile Networks Ltd", "company", "Estates Team"),
        (f"{town} Rovers Football Club", "charity", "Club Secretary"),
        (f"{town} Markets Ltd", "company", "Market Manager"),
        (f"{d.farm} Farming Partnership", "partnership", d.farmers),
        (f"{town} Apps Ltd", "company", "Founder"),
        ("Station Approach Properties Ltd", "company", "Asset Manager"),
    ]


def _numbers(d, plist):
    """Company and charity numbers for the parties, in the ranges used before the districts were added."""
    out, company, charity = [], 0, 0
    for name, ptype, contact in plist:
        co = ch = ""
        if ptype == "company":
            company += 1
            co = f"ZZ000{d.n + 1}{company:02d}"
        elif ptype == "charity":
            charity += 1
            ch = f"ZZ10000{d.n}{charity}"
        out.append((name, ptype, co, ch, contact))
    return out


def load_leases(today):
    """Every district's agreements."""
    from apps.leases.models import Lease

    for d in DISTRICTS:
        load_district_leases(d, today)
    return Lease.objects.filter(reference__startswith="DL-").count()


def load_district_leases(d, today):
    """One district's 23 agreements, with dates relative to today so that reviews, breaks and expiries fall due
    at a realistic mix of times."""
    from apps.core.dates import add_months
    from apps.leases.demo import quarter_day_on_or_before
    from apps.leases.models import BreakOption, Lease, Party

    from .models import Property

    town, L = d.town, d.lease
    party = {}
    shared = ("Example Mobile Networks Ltd", "Station Approach Properties Ltd")
    for i, (name, ptype, co, charity, contact) in enumerate(_numbers(d, parties(d)), start=1):
        slug = name.lower().replace(" ", ".").replace(",", "").replace("&", "and")[:40]
        if name in shared and d is not NORTH:
            party[name] = Party.objects.get(name=name)  # one company, with sites in several districts
            continue
        party[name], _ = Party.objects.update_or_create(name=name, defaults={
            "party_type": ptype, "company_number": co, "charity_number": charity, "contact_name": contact,
            "email": f"{slug}@example.org", "phone": f"01632 960{100 + 100 * d.n + i:03d}",
            "address": f"c/o the demised premises, {town} {d.postcode} 1AA",
            "finance_customer_ref": f"DMC{10000 + 10000 * d.n + i}", "notes": "Fictional demonstration party."})
    P = {p.reference: p for p in Property.objects.filter(reference__startswith=d.prefix)}
    p = d.prefix
    q = quarter_day_on_or_before(today)

    def m(offset):
        return add_months(q, offset + d.shift)

    def lease(ref, props, who, offset, months, **kw):
        start = m(offset)
        kw.setdefault("lease_date", start)
        kw.setdefault("term_start", start)
        if months:
            kw.setdefault("term_end", add_months(start, months) - timedelta(days=1))
        if "annual_rent" in kw:
            kw["annual_rent"] = d.rent(kw["annual_rent"])
        obj, _ = Lease.objects.update_or_create(reference=ref, defaults={"counterparty": party[who], **kw})
        obj.properties.set([P[r] for r in props])
        obj.breaks.all().delete()
        return obj

    park = dict(vat_chargeable=True, repairing="fri", insurance="landlord_recharged", service_charge_payable=True)
    lease(L(1), [f"{p}01-U01"], f"{town} Freight Ltd", -58, 120, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("41600"), review_basis="om_up", review_interval_years=5,
          next_review_date=add_months(m(-58), 60), permitted_use="Storage and distribution", **park)
    l2 = lease(L(2), [f"{p}01-U02"], f"{town} Packaging Ltd", -33, 120, agreement_type="lease",
               security_of_tenure="inside", annual_rent=D("39000"), review_basis="om_up", review_interval_years=5,
               next_review_date=add_months(m(-33), 60), deposit=d.rent("9750"),
               deposit_held="Council rent deposit account", deposit_interest="Tenant, paid annually", **park)
    BreakOption.objects.create(lease=l2, break_date=add_months(m(-33), 60), exercisable_by="tenant",
                               notice_months=6, conditions="No material breach of the repairing covenant.")
    lease(L(3), [f"{p}01-U03"], f"{town} Self Storage Ltd", -110, 180, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("42250"), review_basis="rpi", review_interval_years=5,
          next_review_date=add_months(m(-110), 120), guarantor=party[f"{town} Group plc"],
          permitted_use="Self storage", **park)
    lease(L(5), [f"{p}01-U05"], f"{town} Brewing Co Ltd", -27, 180, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("78000"), review_basis="om_up", review_interval_years=5,
          next_review_date=add_months(m(-27), 60), permitted_use="Brewery and taproom (sui generis)",
          alienation="Assignment of the whole with consent; underletting of part not allowed.", **park)
    lease(L(6), [f"{p}01-U06"], f"{town} Joinery Workshop", -36, 36, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("14400"), rent_frequency="monthly", review_basis="none",
          **park)
    lease(L(7), [f"{p}01-U07"], f"{town} Bikes", -64, 60, agreement_type="lease", status="holding_over",
          security_of_tenure="inside", annual_rent=D("13200"), review_basis="none",
          notes="Holding over. The council intends to oppose renewal on ground (f) to redevelop the block.", **park)
    lease(L(8), [f"{p}01-U08"], f"{town} Ceramics Ltd", -9, 72, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("14800"), review_basis="cpi", review_interval_years=1,
          next_review_date=add_months(m(-9), 12), **park)
    lease(L(9), [f"{p}01-U09"], f"{town} Training Services Ltd", -47, 60, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("15600"), review_basis="none",
          permitted_use="Training centre (Class F1(a))", **park)
    lease(L(4), [f"{p}01-U04"], f"{town} Freight Ltd", -96, 96, agreement_type="lease", status="ended",
          actual_end=add_months(q, -2), security_of_tenure="contracted_out", annual_rent=D("36000"),
          review_basis="none", notes="Ended at expiry. Schedule of dilapidations served.", **park)

    shop = dict(repairing="iri", insurance="landlord_recharged", service_charge_payable=True)
    for k, unit, who, rent, offset, months, basis, every, sec in [
            (11, "U01", "Pharmacy Ltd", 21000, -44, 180, "om_up", 5, "inside"),
            (12, "U02", "News and Post", 11500, -15, 60, "none", None, "contracted_out"),
            (14, "U04", "Bakery", 13000, -52, 120, "om_up", 5, "inside"),
            (15, "U05", "Phone Repairs", 10800, -6, 36, "none", None, "contracted_out"),
            (16, "U06", "Coffee House Ltd", 16500, -23, 120, "om_up", 5, "inside"),
            (18, "U08", "Launderette", 11000, -82, 120, "om_up", 5, "inside")]:
        start = m(offset)
        unit = f"{p}02-{unit}"
        lease(L(k), [unit], f"{town} {who}", offset, months, agreement_type="lease", security_of_tenure=sec,
              annual_rent=D(rent), review_basis=basis, review_interval_years=every,
              next_review_date=add_months(start, 60) if every else None, permitted_use=P[unit].use_description,
              **shop)
    l19 = lease(L(19), [f"{p}02-U09"], f"{town} Training Services Ltd", -30, 72, agreement_type="lease",
                security_of_tenure="inside", annual_rent=D("23400"), vat_chargeable=True, review_basis="om_up",
                review_interval_years=3, next_review_date=add_months(m(-30), 36),
                permitted_use="Offices and training rooms", **shop)
    BreakOption.objects.create(lease=l19, break_date=add_months(m(-30), 36), exercisable_by="either",
                               notice_months=6)

    lease(L(20), [f"{p}04"], f"{town} Leisure Trust", -96, 360, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("0"), rent_frequency="peppercorn", review_basis="none",
          repairing="limited", insurance="landlord", permitted_use="Leisure centre and swimming pool",
          notes="Peppercorn lease with a separate management agreement; the council keeps structural repairs.")
    lease(L(21), [f"{p}05"], f"{town} Community Association", -20, 60, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("600"), rent_frequency="annually", review_basis="none",
          repairing="iri", insurance="landlord", permitted_use="Community hall")
    lease(L(22), [f"{p}07"], "Example Mobile Networks Ltd", -70, 120, agreement_type="lease",
          security_of_tenure="contracted_out", annual_rent=D("4200"), rent_frequency="annually",
          review_basis="fixed", review_interval_years=5, next_review_date=add_months(m(-70), 60),
          repairing="other", insurance="tenant", premises_description="Compound and mast on the water tower site",
          notes="Code agreement; rent assessed on the no-network basis under the Electronic Communications Code.")
    lease(L(23), [f"{p}08"], f"{town} Rovers Football Club", -4, 12, agreement_type="licence",
          security_of_tenure="na", annual_rent=D("1800"), rent_frequency="annually", review_basis="none",
          repairing="landlord", permitted_use="Football matches and training, September to May")
    lease(L(24), [f"{p}09"], f"{town} Markets Ltd", -41, 180, agreement_type="lease",
          security_of_tenure="inside", annual_rent=D("34000"), review_basis="turnover", review_interval_years=1,
          next_review_date=add_months(m(-41), 48), repairing="iri", insurance="landlord_recharged",
          permitted_use="Covered market and ancillary café",
          notes="Base rent plus 8% of stall licence income above £300,000 a year.")
    start = date(today.year if today >= date(today.year, 3, 25) else today.year - 1, 3, 25)
    lease(L(25), [f"{p}10"], f"{d.farm} Farming Partnership", 0, 0, agreement_type="fbt", term_start=start,
          lease_date=start, term_end=date(start.year + 5, 3, 24), security_of_tenure="na", annual_rent=D("9800"),
          rent_frequency="annually", review_basis="om", review_interval_years=3,
          next_review_date=date(start.year + 3, 3, 25), repairing="other", insurance="tenant",
          permitted_use="Agriculture", notes="Five-year farm business tenancy, county farms starter holding.")
    lease(L(31), [f"{p}12-U01"], f"{town} Apps Ltd", -7, 24, agreement_type="licence",
          security_of_tenure="na", annual_rent=D("7200"), rent_frequency="monthly", vat_chargeable=True,
          review_basis="none", repairing="landlord", insurance="landlord", permitted_use="Offices",
          alienation="Personal to the licensee.")
    t = 10 * d.n
    hub = lease(L(30), [f"{p}12"], "Station Approach Properties Ltd", -50, 120, direction="in",
                agreement_type="lease", security_of_tenure="contracted_out", annual_rent=D("38000"),
                review_basis="om_up", review_interval_years=5, next_review_date=add_months(m(-50), 60),
                repairing="fri", insurance="landlord_recharged",
                notes=f"Leased in by the council; see title ZZ2000{t + 1}.")
    BreakOption.objects.create(lease=hub, break_date=add_months(m(-50), 60), exercisable_by="tenant",
                               notice_months=6, conditions="Council's break: rent paid and vacant possession.")
    return Lease.objects.filter(reference__startswith=d.lease_prefix).count()


def unpaid_last(d):
    """Rent ledger: who has fallen behind (number of unpaid recent demands)."""
    return {d.lease(6): 2, d.lease(12): 1, d.lease(18): 2}


def part_paid(d):
    return {d.lease(14): D("0.4")}


def service(d):
    L = d.lease
    return {
        "name": f"{d.town} Business Park services",
        "estate": f"{d.prefix}01",
        "members": [L(1), L(2), L(3), L(5), L(6), L(7), L(8), L(9)],
        "caps": {L(9): D("1800.00")},
        "budget": {"MAN": 4200, "GRN": 7600, "ROAD": 5200, "SEC": 15800, "WASTE": 3300, "INS": 4100, "REP": 6400},
        "factor": {"MAN": 1, "GRN": 0.96, "ROAD": 1.41, "SEC": 1.02, "WASTE": 1.12, "INS": 1, "REP": 0.88},
        "description": "Gatehouse security, estate roads, landscaping, CCTV and shared waste for the business park. "
                       "Fictional demonstration data.",
    }


def valuation_history(d):
    """Valuation history for the top-level properties: (year, value, land, buildings, life, method)."""
    p = d.prefix

    def v(amount):
        return int(d.rent(amount)) if amount else 0

    rows = {
        "01": (2026, 9400000, 2600000, 6800000, 32, "investment"),
        "02": (2026, 3850000, 1100000, 2750000, 28, "investment"),
        "03": (2023, 2150000, 380000, 1770000, 25, "drc"),
        "04": (2022, 8900000, 1200000, 7700000, 22, "drc"),
        "05": (2024, 420000, 110000, 310000, 30, "drc"),
        "06": (2026, 1250000, 1250000, 0, None, "residual"),
        "07": (2026, 62000, 62000, 0, None, "investment"),
        "09": (2026, 2900000, 500000, 2400000, 40, "investment"),
        "10": (2026, 1180000, 1180000, 0, None, "comparison"),
        "11": (2023, 760000, 760000, 0, None, "comparison"),
    }
    out = {}
    for k, (year, _value, land, buildings, life, method) in rows.items():
        land, buildings = v(land), v(buildings)
        out[f"{p}{k}"] = (year, land + buildings, land, buildings, life, method)
    return out


# Everything load_demo_data and the other demo modules need, for all the districts together.
TITLES = [t for d in DISTRICTS for t in titles(d)]
SURVEYORS = {u: name for d in DISTRICTS for u, name in d.surveyors.items()}
ASSIGNMENTS = {k: v for d in DISTRICTS for k, v in assignments(d).items()}
PORTFOLIOS = {k: v for d in DISTRICTS for k, v in portfolios(d).items()}
PHOTOS = {k: v for d in DISTRICTS for k, v in photos(d).items()}
UNPAID_LAST = {k: v for d in DISTRICTS for k, v in unpaid_last(d).items()}
PART_PAID = {k: v for d in DISTRICTS for k, v in part_paid(d).items()}
SERVICES = [service(d) for d in DISTRICTS]
VALUATION_HISTORY = {k: v for d in DISTRICTS for k, v in valuation_history(d).items()}


def surveyors(d=NORTH):
    """Two demonstration surveyors for the district, supervised by the head of estates."""
    from apps.core.models import StaffProfile
    from apps.core.roles import SURVEYORS as ROLE

    users = {}
    for username, (first, last) in d.surveyors.items():
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
    return sum(load_district_cases(d, today) for d in DISTRICTS)


def load_district_cases(d, today):
    """Hand-made cases for one district; lease event cases are opened automatically with Exampleton's."""
    from apps.cases import workflow
    from apps.cases.models import Approval, Case, CaseNote, CaseType, Correspondence
    from apps.leases.models import Lease, Party

    from .models import Property

    if Case.objects.filter(crm_reference__startswith=d.crm).exists():
        return 0
    staff = surveyors(d)
    town, L, p = d.town, d.lease, d.prefix
    t = {c.code: c for c in CaseType.objects.all()}
    lease = {x.reference: x for x in Lease.objects.filter(reference__startswith=d.lease_prefix)}
    P = {x.reference: x for x in Property.objects.filter(reference__startswith=p)}
    head = get_user_model().objects.filter(username="demo.head").first()
    legal = get_user_model().objects.filter(username="demo.legal").first()
    made = 0

    def case(code, title, days_ago, n, **kw):
        nonlocal made
        made += 1
        return workflow.open_case(t[code], title=title, received_on=today - timedelta(days=days_ago),
                                  crm_reference=f"{d.crm}{n}", **kw)

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
    c = case("assignment", f"Consent to assign to {town} Taproom Group Ltd", 3, 1, lease=lease[L(5)],
             how_received=Case.Received.EMAIL)
    Correspondence.objects.create(case=c, direction="in", method="email", on=c.received_on,
                                  correspondent=f"{town} Brewing Co Ltd <accounts@example.org>",
                                  subject="Sale of the business: request for consent to assign",
                                  summary=f"We are selling the brewery to {town} Taproom Group Ltd and ask for "
                                          "the council's consent to assign. Their management accounts are attached.")
    # 2. Change of use of a shop to a vape shop, refused with reasons.
    c = case("change_of_use", "Change of use of 2 The Precinct to a vape shop", 120, 2, lease=lease[L(12)],
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
    c = case("alterations", "Consultation room and new shop front, 1 The Precinct", 26, 3, lease=lease[L(11)],
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
    c = case("dilapidations", f"Dilapidations claim, Unit 4 {town} Business Park", 50, 4, lease=lease[L(4)],
             property=P[f"{p}01-U04"], how_received=Case.Received.LETTER)
    c.stage = "assessing"
    c.dilaps_schedule_value, c.dilaps_served_on = d.rent("68500"), today - timedelta(days=40)
    c.dilaps_response_value, c.dilaps_response_on = d.rent("31000"), today - timedelta(days=6)
    c.dilaps_notes = "Section 18(1) valuation commissioned: the unit will be refurbished before reletting."
    c.save()
    if legal:
        c.contributors.add(legal)
    # 5. A request to buy a strip of the former bus depot.
    c = case("land_purchase", "Request to buy a strip of the former bus depot for garden land", 70, 5,
             property=P[f"{p}06"], how_received=Case.Received.EMAIL)
    c.acknowledged_on, c.stage = c.received_on + timedelta(days=6), "gathering"
    c.save()
    CaseNote.objects.create(case=c, text="Neighbour at 14 Depot Road. Check whether a sale would prejudice the wider "
                                         "disposal and whether the strip is in the contaminated area.")
    # 6. A wayleave request for a new fibre cable.
    c = case("wayleave", "Wayleave for a fibre cable across the business park verge", 18, 6,
             property=P[f"{p}01-L01"],
             party=Party.objects.filter(name="Example Mobile Networks Ltd").first(), how_received=Case.Received.EMAIL)
    c.acknowledged_on, c.stage = c.received_on + timedelta(days=1), "gathering"
    c.save()
    # 7. A breach of the user clause at the market hall: past target.
    c = case("breach", "Market hall used for late-night events without consent", 75, 7, lease=lease[L(24)],
             how_received=Case.Received.PHONE)
    c.stage, c.target_date = "assessing", today - timedelta(days=12)
    c.save()
    CaseNote.objects.create(case=c, text="Residents' complaints logged with environmental health. Warning letter "
                                         "drafted; waiting for the operator's licence details.")
    # 8. A service charge query on the business park.
    c = case("sc_dispute", "Query about the 2025/26 security patrol costs", 14, 8, lease=lease[L(2)],
             how_received=Case.Received.EMAIL)
    c.acknowledged_on = c.received_on + timedelta(days=2)
    c.save()
    # 9. A new letting of Studio 2: heads of terms nearly complete, conflict declared.
    c = case("new_letting", "New licence of Studio 2, Innovation Hub", 22, 9, property=P[f"{p}12-U02"],
             how_received=Case.Received.ONLINE)
    c.acknowledged_on, c.stage, c.tenant_represented = c.received_on + timedelta(days=2), "assessing", "yes"
    c.heads_of_terms = {"premises": "Studio 2 as shown on the plan", "term": "12-month licence, renewable",
                        "rent": f"£{d.rent('7200'):,.0f} a year, monthly in advance, including service costs",
                        "vat": "VAT charged", "security": "One month's licence fee",
                        "repairs": "Licensor repairs; licensee keeps tidy",
                        "service_insurance": "Included in the licence fee"}
    c.save()
    lead, second = (staff[u].get_full_name() for u in (d.lead, d.second))
    declare(c, "The applicant's director is a former council employee who worked in the estates team. "
               f"{lead} negotiates; {second} checks the terms.")
    # 10. Renewal opposed on redevelopment grounds.
    c = case("renewal", "Renewal of Unit 7: opposed on ground (f)", 60, 10, lease=lease[L(7)],
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
    from apps.maintenance.models import Job

    for d in DISTRICTS:
        load_district_maintenance(d, today)
    return Job.objects.filter(property__reference__startswith="DM-").count()


def load_district_maintenance(d, today):
    from apps.core.dates import add_months
    from apps.maintenance import library, workflow
    from apps.maintenance.models import Component, Contract, Contractor, Job, PlannedTask, Responsibility

    from .models import Property

    p = d.prefix
    if Component.objects.filter(property__reference__startswith=p).exists():
        return 0
    P = {x.reference: x for x in Property.objects.filter(reference__startswith=p)}
    c = {x.finance_supplier_ref.split("-", 1)[1].lower(): x
         for x in Contractor.objects.filter(finance_supplier_ref__startswith="DEMO-")}
    # Two contractors shared by the districts, added with Northfield's data.
    for key, name, trades, days in [("grounds", "Northfield Grounds and Drainage Ltd", "Grounds, drains, gullies", 120),
                                    ("glazing", "Clearview Glazing Northfield", "Glazing, shop fronts, shutters", 12)]:
        if key not in c:
            c[key] = Contractor.objects.create(
                name=name, trades=trades, contact_name="Service desk", email=f"{key}@example.org",
                phone="01632 960050", emergency_phone="01632 960051", insurer="Example Mutual Insurance",
                public_liability=D("5000000"), insurance_expires=today + timedelta(days=days),
                finance_supplier_ref=f"DEMO-{key.upper()}", notes="Fictional demonstration contractor.")
    plant = Contract.objects.create(contractor=c["heating"], title="Leisure centre and library plant maintenance",
                                    reference=f"{d.abbr}/MECH/24", starts=add_months(today, -20 + d.shift),
                                    ends=add_months(today, 4 + d.shift), annual_value=d.rent("31500"))
    plant.properties.add(P[f"{p}03"], P[f"{p}04"])
    grounds = Contract.objects.create(contractor=c["grounds"], title="Business park grounds and gully cleaning",
                                      reference=f"{d.abbr}/GRND/25", starts=add_months(today, -8),
                                      ends=add_months(today, 28), annual_value=d.rent("9600"), service_charge=True)
    grounds.properties.add(P[f"{p}01"])

    comp = {}
    for ref, name, cat, loc, installed, life, cond, cost in [
            ("04", "Pool filtration and dosing plant", "mechanical", "Pool plant room", 2006, 20, "C", 240000),
            ("04", "Main hall roof (profiled metal)", "roof", "Sports hall", 1998, 30, "C", 310000),
            ("04", "Air handling units (3)", "mechanical", "Roof plant deck", 2011, 20, "B", 180000),
            ("03", "Flat roof (asphalt)", "roof", "Whole building", 1987, 25, "D", 95000),
            ("03", "Electrical distribution", "electrical", "Whole building", 1999, 30, "B", 70000),
            ("03", "Passenger lift", "lift", "Stair core", 2008, 25, "B", 65000),
            ("01-B01", "Roller shutter doors (5)", "external", "Loading bays", 2008, 20, "C", 45000),
            ("09", "Glazed roof lantern", "roof", "Market floor", 1890, 40, "C", 220000),
            ("02-B01", "Shop front shutters", "external", "Ground floor", 2014, 15, "B", 36000)]:
        comp[name] = Component.objects.create(
            property=P[p + ref], name=name, category=cat, location=loc, installed_year=installed, life_years=life,
            condition=cond, condition_on=today - timedelta(days=150), replacement_cost=d.rent(cost), capital=True)

    for ref, code, due, contractor, contract in [
            ("04", "legionella_ra", 35, "heating", plant), ("04", "water_temps", -3, "heating", plant),
            ("04", "fire_alarm", 50, "electrical", None), ("04", "boiler_service", 80, "heating", plant),
            ("04", "aircon_tm44", 600, "heating", None), ("03", "lift_exam", 12, "heating", plant),
            ("03", "lift_service", 40, "heating", plant), ("03", "emergency_lighting", -20, "electrical", None),
            ("03", "asbestos", 75, None, None), ("09", "fire_doors", 30, "building", None),
            ("01-L01", "drains", 55, "grounds", grounds), ("01-B01", "roof_gutters", 95, "roofing", None),
            ("02-B01", "eicr", 300, "electrical", None)]:
        _code, title, category, months, statutory, regulation = library.BY_CODE[code]
        next_due = today + timedelta(days=due + 7 * d.shift)
        PlannedTask.objects.create(
            property=P[p + ref], title=title, category=category, frequency_months=months, statutory=statutory,
            regulation=regulation, contractor=c.get(contractor), contract=contract, next_due=next_due,
            last_done=add_months(next_due, -months), estimated_cost=D("420") if months <= 12 else D("1600"))
    workflow.auto_raise(today)

    head = get_user_model().objects.filter(username="demo.head").first()
    town = d.town

    def job(ref, title, **fields):
        return workflow.open_job(P[p + ref], title, **fields)

    j = job("04", "Pool hall ceiling tile fallen near the learner pool", category="internal",
            priority="emergency", reported_on=today - timedelta(days=1), how_reported="phone",
            reported_by=f"Duty manager, {town} Leisure Trust", contractor=c["building"], estimate=D("900"),
            description="Learner pool closed. Check the remaining tiles and the ceiling grid for corrosion.")
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=1))
    job("03", "Damp patch spreading on the children's library ceiling", category="roof", priority="urgent",
        reported_on=today - timedelta(days=12), how_reported="email", reported_by="Library manager",
        component=comp["Flat roof (asphalt)"], contractor=c["roofing"], estimate=D("2400"))
    j = job("01-U02", "Roller shutter will not close fully", category="external", priority="urgent",
            reported_on=today - timedelta(days=16), how_reported="tenant", reported_by=f"{town} Packaging Ltd",
            component=comp["Roller shutter doors (5)"], contractor=c["building"], estimate=D("780"))
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=15))
    j = job("02-U06", "Shop front window cracked by a shopping trolley", category="external",
            priority="routine", reported_on=today - timedelta(days=45), how_reported="tenant",
            contractor=c["glazing"], estimate=D("560"), responsibility=Responsibility.TENANT,
            responsibility_reason="Internal repairing lease: the tenant repairs the shop front glass")
    j = job("01-L01", "Blocked gully flooding the estate road", category="ext_works", priority="urgent",
            reported_on=today - timedelta(days=28), how_reported="inspection", contractor=c["grounds"],
            estimate=D("350"))
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=28))
    workflow.complete(j, today - timedelta(days=25), D("395"), "Gully jetted and silt trap cleared.",
                      f"NGD-{2210 + 100 * (d.n - 1)}")
    j = job("09", "Replace cracked panes in the roof lantern", category="roof", priority="planned",
            reported_on=today - timedelta(days=8), how_reported="inspection", contractor=c["glazing"],
            estimate=d.rent("14800"), component=comp["Glazed roof lantern"],
            description="Twelve cracked panes found at the condition survey. Listed building consent may be needed.")
    if head and j.owner and j.owner != head:
        j.approval_status, j.approver = "pending", head
        j.save()
    j = job("01-U06", "Graffiti on the workshop roller shutter", category="external", priority="routine",
            reported_on=today - timedelta(days=60), how_reported="inspection", contractor=c["building"],
            estimate=D("180"), responsibility=Responsibility.RECHARGE,
            responsibility_reason="Tenant's covenant to keep the shutter clean: recharge")
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=58))
    workflow.complete(j, today - timedelta(days=50), D("180"), "Graffiti removed and shutter resprayed.",
                      f"RBM-{4520 + 100 * (d.n - 1)}")
    j = job("04", "Main pool circulation pump failure", category="mechanical", priority="emergency",
            reported_on=today - timedelta(days=90), how_reported="phone", contractor=c["heating"],
            estimate=D("3200"), component=comp["Pool filtration and dosing plant"])
    workflow.issue_order(j, email_contractor=False, on=today - timedelta(days=90))
    workflow.complete(j, today - timedelta(days=88), D("3460"), "Pump replaced; pool reopened after water tests.",
                      f"HWM-{1302 + 100 * (d.n - 1)}")
    j.status = Job.Status.CLOSED
    j.save()
    job("05", "Hall heating not reaching temperature", category="mechanical", priority="routine",
        reported_on=today - timedelta(days=4), how_reported="email", reported_by="Hall bookings secretary")
    load_district_surveys(d, today, P, comp)
    return Job.objects.filter(property__reference__startswith=p).count()


def load_district_surveys(d, today, P, comp):
    """Condition surveys: the library and leisure centre surveyed last year (finished, with work outstanding), the
    market hall surveyed six years ago (overdue for another) and a survey of the community hall still being entered."""
    from apps.core.dates import add_months
    from apps.maintenance import surveys
    from apps.maintenance.models import ConditionSurvey, SurveyItem

    p, town = d.prefix, d.town
    firm = "J Patel MRICS, Example Building Surveyors LLP (fictional)"
    plans = [
        ("03", add_months(today, -14), "C", "finished", [
            ("roof", "Flat roof", "Strip and renew the asphalt roof covering with insulation to current standards",
             "D", 1, 95000, True, "Flat roof (asphalt)"),
            ("electrical", "Whole building", "Replace the 1999 distribution boards and test the installation",
             "B", 3, 18000, True, "Electrical distribution"),
            ("internal", "Children's library", "Make good water-damaged ceiling after the roof is renewed",
             "C", 2, 4500, False, None),
            ("external", "Rear entrance", "Ramp and handrails for step-free access", "C", 2, 12500, True, None),
            ("external", "First floor", "Overhaul window ironmongery and seals", "B", 4, 3200, False, None)]),
        ("04", add_months(today, -10), "C", "finished", [
            ("mechanical", "Pool plant room", "Replace pool filtration and dosing plant", "C", 2, 240000, True,
             "Pool filtration and dosing plant"),
            ("roof", "Sports hall", "Overclad the profiled metal roof; renew gutters and outlets", "C", 2, 310000, True,
             "Main hall roof (profiled metal)"),
            ("internal", "Changing rooms", "Refit changing rooms and showers", "C", 3, 85000, True, None),
            ("fire", "Plant room door", "Replace damaged fire door and closer", "D", 1, 1800, False, None)]),
        ("09", add_months(today, -74), "B", "finished", [
            ("roof", "Market floor", "Repair cracked panes in the glazed roof lantern", "C", 2, 14800, False,
             "Glazed roof lantern")]),
        ("05", today - timedelta(days=6), "", "draft", [
            ("mechanical", "Main hall", "Replace the gas boiler, near the end of its life", "C", 2, 9500, True,
             None)]),
    ]
    for ref, when, grade, status, items in plans:
        survey = ConditionSurvey.objects.create(property=P[p + ref], surveyed_on=when, surveyor=firm,
                                                overall_grade=grade,
                                                notes=f"Fictional survey of {P[p + ref].name}, {town}.")
        for element, location, text, g, priority, cost, capital, component in items:
            SurveyItem.objects.create(survey=survey, element=element, location=location, description=text, grade=g,
                                      priority=priority, estimated_cost=d.rent(cost), capital=capital,
                                      component=comp.get(component) if component else None)
        if status == "finished":
            surveys.finish(survey, update_components=False)
            survey.finished_on = when + timedelta(days=21)
            survey.save(update_fields=["finished_on"])
    # The leisure centre's fire door has since been replaced.
    door = SurveyItem.objects.filter(survey__property=P[p + "04"], element="fire").first()
    if door:
        door.state, door.state_note = SurveyItem.State.DONE, "Replaced by the leisure trust's contractor."
        door.save(update_fields=["state", "state_note"])


def load_compliance(today):
    return sum(load_district_compliance(d, today) for d in DISTRICTS)


def load_district_compliance(d, today):
    from django.core.files.base import ContentFile

    from apps.compliance import workflow
    from apps.compliance.models import Action, BuildingDocument, BuildingSafety, Certificate, ComplianceType

    from .demo_media import placeholder_pdf
    from .models import Property

    p, town = d.prefix, d.town
    P = {x.reference: x for x in Property.objects.filter(reference__startswith=p)}
    if not P or BuildingSafety.objects.filter(property__in=P.values()).exists():
        return 0
    kinds = {k.code: k for k in ComplianceType.objects.all()}
    plan = {
        "04": ["fra", "fire_alarm", "emergency_lighting", "gas", "eicr", "legionella", "asbestos", "pressure",
               "tm44", "dec"],
        "03": ["fra", "fire_alarm", "emergency_lighting", "eicr", "asbestos", "lift", "dec"],
        "09": ["fra", "eicr", "asbestos", "epc"],
        "02-B01": ["fra", "eicr", "asbestos"],
        "05": ["fra", "gas", "eicr", "epc"],
        "01-U04": ["epc"], "01-U10": ["epc"], "02-U03": ["epc"], "02-U07": ["epc"],
        "12-U02": ["epc"],
    }
    reqs = {}
    for ref, codes in plan.items():
        for req in workflow.add_requirements(P[p + ref], [kinds[c] for c in codes]):
            reqs[(ref, req.kind.code)] = req

    # Westbrook's certificates were renewed a month earlier and Kingsmere's two months later, so different
    # ones fall due.
    lag = {1: 0, 2: 1, 3: -2}[d.n]

    def cert(ref, code, months_ago, result="ok", rating="", actions=(), by="Fictional inspector"):
        from apps.core.dates import add_months

        req = reqs[(ref, code)]
        c = Certificate(requirement=req, issued_on=add_months(today, -max(0, months_ago + lag)), result=result,
                        rating=rating, carried_out_by=by, reference=f"DEMO-{code.upper()}-{req.pk}")
        c.file.save(f"{code}.pdf", ContentFile(placeholder_pdf(f"{req.kind.name}, {req.property.name}",
                                                               ["A fictional document for demonstrating PHAEMA."],
                                                               banner="FICTIONAL DEMONSTRATION DOCUMENT")), save=False)
        c.original_filename = f"{code}.pdf"
        c.save()
        for text, priority, done in actions:
            Action.objects.create(certificate=c, description=text, priority=priority,
                                  done_on=c.issued_on + timedelta(days=20) if done else None)
        return c

    cert("04", "fra", 4, "actions", actions=[
        ("Clear stored equipment from the escape route behind the sports hall", "high", False),
        ("Repair the self-closer on the plant room door", "medium", True)], by=f"{town} Leisure Trust")
    cert("04", "fire_alarm", 3)
    cert("04", "emergency_lighting", 13)            # expired
    cert("04", "gas", 8)
    cert("04", "eicr", 40, "actions", actions=[("Replace corroded pool hall light fittings (C2)", "medium", False)])
    cert("04", "legionella", 10)                     # expires soon
    cert("04", "asbestos", 6)
    cert("04", "pressure", 7)
    cert("04", "dec", 5, rating="D")
    # <code>04 TM44 air conditioning inspection: missing
    cert("03", "fra", 14)                            # expired
    cert("03", "fire_alarm", 5)
    cert("03", "emergency_lighting", 2)
    cert("03", "eicr", 55, "fail")                   # unsatisfactory and out of date
    cert("03", "asbestos", 9, "actions", actions=[("Label the AIB ceiling panels in the first floor void", "high",
                                                   False)])
    cert("03", "lift", 5)
    cert("03", "dec", 8, rating="F")
    cert("09", "fra", 2)
    cert("09", "eicr", 18)
    cert("09", "epc", 30, rating="E")
    # <code>09 asbestos: missing
    cert("02-B01", "fra", 11)
    cert("02-B01", "eicr", 44)
    cert("02-B01", "asbestos", 20)
    cert("05", "fra", 7, by=f"{town} Community Association")
    cert("05", "gas", 12, by=f"{town} Community Association")  # expires about now
    cert("05", "eicr", 22)
    cert("05", "epc", 70, rating="D")
    cert("01-U04", "epc", 100, rating="G")           # expired and below the letting minimum
    cert("01-U10", "epc", 15, rating="B")
    cert("02-U03", "epc", 50, rating="C")
    cert("02-U07", "epc", 80, rating="F")            # below the letting minimum
    # <code>12-U02 EPC: missing, with a new letting case open

    for ref, height, storeys, homes, tier, rp in [
            ("04", "11.0", 2, 0, "B", f"{town} Leisure Trust (day to day); council (structure)"),
            ("03", "8.5", 2, 0, "B", "Exampleton Council, Facilities"),
            ("02-B01", "10.5", 3, 0, "B", "Exampleton Council, Estates"),
            ("09", "14.0", 2, 0, "B", f"{town} Markets Ltd"),
            ("06", None, None, 0, "C", "")]:
        prop = P[p + ref]
        BuildingSafety.objects.create(property=prop, height_m=height, storeys=storeys, residential_units=homes,
                                      tier=tier, confirmed_on=today - timedelta(days=45),
                                      confirmed_by=prop.managing_surveyor, responsible_person=rp)
    for ref, category, title, year in [
            ("03", "asbestos", "Asbestos register and management plan", 2024),
            ("03", "plans", "Library floor plans", 1987),
            ("04", "om", "Pool plant operation and maintenance manual", 2006),
            ("04", "fire", "Fire strategy drawings", 2011),
            ("04", "risk", "Pool safety operating procedure (normal and emergency action plans)", 2025),
            ("09", "survey", "Condition survey of the market hall", 2026),
            ("06", "survey", "Phase 2 ground investigation report", 2025)]:
        doc = BuildingDocument(property=P[p + ref], category=category, title=title, document_date=date(year, 5, 1),
                               original_filename=f"{category}.pdf")
        doc.file.save(f"{category}.pdf", ContentFile(placeholder_pdf(title, ["A fictional document for "
                                                                             "demonstrating PHAEMA."],
                                                                     banner="FICTIONAL DEMONSTRATION DOCUMENT")),
                      save=False)
        doc.save()
    return len(reqs)


def load_valuations(today):
    for d in DISTRICTS:
        load_district_valuations(d, today)


def load_district_valuations(d, today):
    """Give the district's assets to its lead surveyor and raise one open audit query."""
    from apps.valuations import workflow
    from apps.valuations.models import Valuation, ValuationSettings

    p = d.prefix
    year_end = ValuationSettings.load().year_end(today)
    users = {u.username: u for u in get_user_model().objects.filter(username__in=(d.lead, "demo.head"))}
    if d.lead in users:
        mine = workflow.staff_valuer(users[d.lead])
        for ref in (f"{p}07", f"{p}10"):  # in this year's programme; the lead surveyor manages both
            v = Valuation.objects.filter(property__reference=ref, valuation_date=year_end).first()
            if v and v.valuer_id != mine.pk:
                workflow.assign(v, mine)
    last = Valuation.objects.filter(property__reference=f"{p}09", valuation_date__lt=year_end,
                                    status="accepted").order_by("-valuation_date").first()
    if last and "demo.head" in users and not last.audit_reviews.exists():
        workflow.flag(last, users["demo.head"], "Please explain the turnover rent assumption and the yield applied "
                      "to the market hall.", "query", "Example Audit LLP (fictional)", today + timedelta(days=21))
