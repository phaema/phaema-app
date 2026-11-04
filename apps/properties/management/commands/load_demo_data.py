# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load a fictional council's estate for demonstrations and testing.

Everything here is invented: the council, the town of Exampleton, the addresses
(ZZ99 pseudo-postcodes), UPRNs (9999… numbers) and title numbers (ZZ prefix, which
HM Land Registry does not use). Grid references place the estate in the Midlands
so the map has somewhere to show it.

    python manage.py load_demo_data            # add or refresh the demo records
    python manage.py load_demo_data --reset    # remove the demo records first
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import ModuleSettings
from apps.core.roles import SURVEYORS as SURVEYOR_ROLE
from apps.properties.demo_media import placeholder_pdf, placeholder_photo
from apps.properties.models import InspireParcel, Property, PropertyPhoto, Title, TitleDocument

PREFIX = "DM-"
TITLE_PREFIX = "ZZ"
ORG_NAME = "Demonstration District Council"
TOWN = "Exampleton"

# Origin for the fictional town (British National Grid, metres).
E0, N0 = 445000, 295000


def rect(dx, dy, width, height):
    """A rectangle offset from the town origin, as a MultiPolygon in EPSG:27700."""
    x, y = E0 + dx, N0 + dy
    ring = ((x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y))
    return MultiPolygon(Polygon(ring, srid=27700), srid=27700)


def hectares(geom):
    return Decimal(geom.area / 10000).quantize(Decimal("0.0001"))


_uprn_counter = iter(range(999900000101, 999900009999))


def uprn():
    return str(next(_uprn_counter))


def build_records():
    """Return the demo properties as dicts, parents before children."""
    records = []

    def add(ref, name, ptype, parent=None, **fields):
        geom = fields.get("boundary")
        if geom is not None and ptype in ("estate", "site", "land") and "site_area_ha" not in fields:
            fields["site_area_ha"] = hectares(geom)
        fields.setdefault("town", TOWN)
        records.append({"reference": ref, "name": name, "property_type": ptype, "parent": parent, **fields})

    # 1. Riverside Industrial Estate: estate > blocks > units
    add("DM-E01", "Riverside Industrial Estate", "estate", holding_purpose="investment",
        tenure="freehold", occupation="part_let", use_description="Industrial estate",
        address_line_1="Riverside Way", postcode="ZZ99 1RE", usrn="99990001", boundary=rect(0, 0, 320, 190),
        notes="Council-built estate of light industrial units, let on full repairing leases.")
    for block, (bx, by, units) in {"A": (20, 20, [("1", "let", 480), ("2", "let", 480), ("3", "vacant", 480), ("4", "let", 960)]),
                                   "B": (20, 110, [("5", "let", 320), ("6", "let", 320), ("7", "let", 320), ("8", "vacant", 640)])}.items():
        bref = f"DM-E01-B0{1 if block == 'A' else 2}"
        width = 70 * len(units)
        add(bref, f"Unit block {block}", "building", "DM-E01", holding_purpose="investment", tenure="freehold",
            occupation="part_let", use_description="Light industrial", use_class="E(g)(iii)",
            address_line_1=f"Block {block}, Riverside Way", postcode="ZZ99 1RE",
            gia_sqm=Decimal(sum(u[2] for u in units)) * Decimal("1.12"), boundary=rect(bx, by, width, 60))
        for i, (num, occ, nia) in enumerate(units):
            add(f"DM-E01-U0{num}", f"Unit {num}", "unit", bref, uprn=uprn(), holding_purpose="investment",
                tenure="freehold", occupation=occ, use_description="Light industrial / storage",
                use_class="B8" if int(num) % 2 == 0 else "E(g)(iii)",
                address_line_1=f"Unit {num}, Riverside Way", postcode="ZZ99 1RE",
                nia_sqm=Decimal(nia), gia_sqm=Decimal(nia) * Decimal("1.05"),
                boundary=rect(bx + 70 * i, by, 70, 60))
    add("DM-E01-L01", "Estate roads and landscaping", "land", "DM-E01", holding_purpose="operational",
        tenure="freehold", occupation="na", use_description="Estate roads", boundary=rect(0, 80, 320, 30),
        notes="Unadopted estate roads maintained by the council; costs recoverable through the service charge.")

    # 2. Market Square shopping parade
    add("DM-S01", "Market Square shopping parade", "site", holding_purpose="investment", tenure="freehold",
        occupation="part_let", use_description="Retail parade", address_line_1="Market Square",
        postcode="ZZ99 1MS", usrn="99990002", boundary=rect(600, 400, 120, 40))
    add("DM-S01-B01", "1–6 Market Square", "building", "DM-S01", uprn=uprn(), holding_purpose="investment",
        tenure="freehold", occupation="part_let", use_description="Shops with offices over",
        address_line_1="1–6 Market Square", postcode="ZZ99 1MS", gia_sqm=Decimal("1180"),
        boundary=rect(600, 400, 120, 25))
    shops = [("1", "Café", "let", 85), ("2", "Shop", "let", 72), ("3", "Shop", "vacant", 72),
             ("4", "Hairdresser", "let", 64), ("5", "Shop", "let", 72), ("6", "Takeaway", "let", 90)]
    for i, (num, use, occ, nia) in enumerate(shops):
        add(f"DM-S01-U0{num}", f"{num} Market Square", "unit", "DM-S01-B01", uprn=uprn(),
            holding_purpose="investment", tenure="freehold", occupation=occ, use_description=use,
            use_class="Sui generis" if use == "Takeaway" else "E(a)" if use == "Shop" else "E(b)" if use == "Café" else "E(c)",
            address_line_1=f"{num} Market Square", postcode="ZZ99 1MS", nia_sqm=Decimal(nia),
            gia_sqm=Decimal(nia) * Decimal("1.10"),
            boundary=rect(600 + 20 * i, 400, 20, 25))
    add("DM-S01-U07", "First floor offices, 1–6 Market Square", "unit", "DM-S01-B01", uprn=uprn(),
        holding_purpose="investment", tenure="freehold", occupation="let", use_description="Office",
        use_class="E(g)(i)", address_line_1="First floor, 1–6 Market Square", postcode="ZZ99 1MS",
        nia_sqm=Decimal("390"))

    # 3. Operational property
    add("DM-S02", "Exampleton Town Hall", "building", uprn=uprn(), holding_purpose="operational",
        tenure="freehold", occupation="council", use_description="Council offices", use_class="E(g)(i)",
        address_line_1="High Street", postcode="ZZ99 1TH", gia_sqm=Decimal("4250"),
        boundary=rect(520, 470, 60, 45), notes="Listed building (Grade II). Civic offices and council chamber.")
    add("DM-S03", "Station Road multi-storey car park", "site", uprn=uprn(), holding_purpose="operational",
        tenure="freehold", occupation="council", use_description="Car park (420 spaces)",
        address_line_1="Station Road", postcode="ZZ99 1SR", gia_sqm=Decimal("11800"),
        boundary=rect(760, 330, 90, 60))
    add("DM-S04", "Mill Lane depot", "site", uprn=uprn(), holding_purpose="operational", tenure="freehold",
        occupation="council", use_description="Waste and grounds maintenance depot", use_class="B8",
        address_line_1="Mill Lane", postcode="ZZ99 2ML", gia_sqm=Decimal("1650"),
        boundary=rect(-400, -150, 150, 110))
    add("DM-S09", "Confidential service property", "building", uprn=uprn(), holding_purpose="operational",
        tenure="freehold", occupation="council", use_description="Confidential council service",
        address_line_1="Address withheld", postcode="ZZ99 9ZZ", gia_sqm=Decimal("310"),
        exclude_from_publication=True,
        notes="Sensitive location: excluded from the Transparency Code register and other open data.")

    # 4. Community property
    add("DM-S05", "Brookside Community Centre", "building", uprn=uprn(), holding_purpose="community",
        tenure="freehold", occupation="let", use_description="Community centre", use_class="F2(b)",
        address_line_1="Brook Lane", postcode="ZZ99 3BL", gia_sqm=Decimal("620"),
        boundary=rect(900, 700, 40, 30),
        notes="Let to Brookside Community Association at a peppercorn rent on a 25-year lease.")
    add("DM-S08", "Hill Road allotments", "land", holding_purpose="community", tenure="freehold",
        occupation="let", use_description="Allotments (46 plots)", address_line_1="Hill Road",
        postcode="ZZ99 3HR", boundary=rect(1000, 900, 160, 110),
        notes="Statutory allotments, let to Exampleton Allotment Society. Disposal needs Secretary of State consent.")

    # 5. Surplus and investment land
    add("DM-S06", "Former Oak Street school site", "land", holding_purpose="held_for_sale", tenure="freehold",
        occupation="vacant", use_description="Cleared development site", address_line_1="Oak Street",
        postcode="ZZ99 4OS", boundary=rect(300, 800, 140, 100),
        notes="Declared surplus. Subject to a planning brief for about 40 homes; best consideration required (s123).")
    add("DM-S10", "Grazing land at Lower Farm", "land", holding_purpose="investment", tenure="freehold",
        occupation="let", use_description="Agricultural grazing", address_line_1="Lower Farm Lane",
        postcode="ZZ99 5LF", boundary=rect(-900, 600, 420, 300),
        notes="Let on a farm business tenancy, renewed annually.")
    add("DM-S11", "Riverside café kiosk", "building", uprn=uprn(), holding_purpose="investment",
        tenure="freehold", occupation="let", use_description="Kiosk café", use_class="E(b)",
        address_line_1="Riverside Walk", postcode="ZZ99 1RW", gia_sqm=Decimal("38"),
        boundary=rect(350, 220, 8, 6))

    # 6. Enterprise Centre: held on a long lease, sub-let as small offices
    add("DM-S07", "Exampleton Enterprise Centre", "building", uprn=uprn(), holding_purpose="investment",
        tenure="leasehold", occupation="part_let", use_description="Small business offices", use_class="E(g)(i)",
        address_line_1="Enterprise Way", postcode="ZZ99 6EW", gia_sqm=Decimal("1450"),
        boundary=rect(150, 500, 50, 35),
        site_hazards="Flat roof is fragile in places: roof access only with the facilities team and a permit. "
                     "Plant room in the basement is a confined space.",
        notes="Held by the council on a 125-year ground lease; suites let on short business leases outside the 1954 Act.")
    for i, (occ, nia) in enumerate([("let", 45), ("let", 45), ("vacant", 60), ("let", 120)], start=1):
        add(f"DM-S07-U0{i}", f"Suite {i}, Enterprise Centre", "unit", "DM-S07", uprn=uprn(),
            holding_purpose="investment", tenure="leasehold", occupation=occ, use_description="Office suite",
            use_class="E(g)(i)", address_line_1=f"Suite {i}, Enterprise Way", postcode="ZZ99 6EW",
            nia_sqm=Decimal(nia), gia_sqm=Decimal(nia) * Decimal("1.08"))
    return records


TITLES = [
    {"title_number": "ZZ100001", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 101",
     "restrictions_and_covenants": "Restrictive covenant against use as a scrap metal yard (conveyance 1968).",
     "refs": ["DM-E01"]},
    {"title_number": "ZZ100002", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 102",
     "restrictions_and_covenants": "Rights of way for the adjoining owner over the rear service yard.",
     "refs": ["DM-S01", "DM-S11"]},
    {"title_number": None, "tenure": "freehold", "title_class": "unregistered",
     "deeds_location": "Legal Services strongroom, packet 7 (pre-1900 deeds)",
     "restrictions_and_covenants": "Not yet registered. Voluntary first registration recommended.",
     "refs": ["DM-S02"]},
    {"title_number": "ZZ100003", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Digital copy only", "refs": ["DM-S03", "DM-S04"]},
    {"title_number": "ZZ100004", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 140",
     "restrictions_and_covenants": "Land held for allotment purposes.", "refs": ["DM-S05", "DM-S08"]},
    {"title_number": "ZZ100005", "tenure": "freehold", "title_class": "possessory",
     "deeds_location": "Digital copy only",
     "restrictions_and_covenants": "Possessory title to the northern strip; consider title indemnity insurance on disposal.",
     "refs": ["DM-S06"]},
    {"title_number": "ZZ100006", "tenure": "freehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 155", "refs": ["DM-S10", "DM-S09"]},
    {"title_number": "ZZ200001", "tenure": "leasehold", "title_class": "absolute",
     "deeds_location": "Legal Services strongroom, packet 210",
     "restrictions_and_covenants": "125-year ground lease from 2004; landlord's consent needed to assign the head lease.",
     "refs": ["DM-S07"]},
]


# Fictional managing surveyors. They cannot sign in (no password is set).
SURVEYORS = {
    "demo.amorgan": ("Alex", "Morgan"),
    "demo.pshah": ("Priya", "Shah"),
    "demo.ojones": ("Owen", "Jones"),
}
# Which surveyor manages which demo property (children inherit unless listed).
ASSIGNMENTS = {
    "DM-E01": "demo.amorgan", "DM-S11": "demo.amorgan", "DM-S07": "demo.amorgan",
    "DM-S01": "demo.pshah", "DM-S05": "demo.pshah", "DM-S08": "demo.pshah",
    "DM-S02": "demo.ojones", "DM-S03": "demo.ojones", "DM-S04": "demo.ojones", "DM-S09": "demo.ojones",
    # DM-S06 and DM-S10 are left unassigned to show the "Unassigned" filter.
}

PHOTOS = {
    "DM-E01": [("Riverside Industrial Estate from the entrance", "industrial")],
    "DM-E01-U03": [("Unit 3 front elevation", "industrial"), ("Unit 3 loading door", "industrial"),
                   ("Unit 3 yard", "industrial")],
    "DM-S01-B01": [("1–6 Market Square from the square", "retail"), ("Shop fronts, east end", "retail"),
                   ("Shop fronts, west end", "retail")],
    "DM-S02": [("Town Hall front elevation", "civic"), ("Town Hall from High Street", "civic")],
    "DM-S06": [("Former Oak Street school site from Oak Street", "land")],
}

DOCUMENTS = {
    "ZZ100001": [
        ("register", "Official copy of the register", date(2026, 3, 14), [
            "Title number ZZ100001", "Property: Riverside Industrial Estate, Riverside Way, Exampleton ZZ99 1RE",
            "Proprietor: Demonstration District Council", "Class of title: Title absolute",
            "Charges register: Restrictive covenant against use as a scrap metal yard (conveyance 1968)."]),
        ("plan", "Title plan", date(2026, 3, 14), [
            "Title number ZZ100001", "Title plan placeholder: boundaries shown in the PHAEMA map."]),
    ],
    "ZZ200001": [
        ("lease", "Ground lease of the Enterprise Centre", date(2004, 6, 24), [
            "Lease dated 24 June 2004", "Landlord: Exampleton Estates (fictional)",
            "Tenant: Demonstration District Council", "Term: 125 years from 24 June 2004",
            "Rent: peppercorn", "Alienation: landlord's consent needed to assign the whole."]),
    ],
}


class Command(BaseCommand):
    help = "Load a fictional council's estate (Exampleton) for demonstrations and testing."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove existing demo records first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            removed = self.remove_demo_data()
            self.stdout.write(f"Removed {removed} demo records.")

        refs = {}
        created = updated = 0
        for rec in build_records():
            rec = dict(rec)
            parent_ref = rec.pop("parent")
            rec["parent"] = refs[parent_ref] if parent_ref else None
            reference = rec.pop("reference")
            obj, was_created = Property.objects.update_or_create(reference=reference, defaults=rec)
            refs[reference] = obj
            created += was_created
            updated += not was_created

        for spec in TITLES:
            spec = dict(spec)
            linked = [refs[r] for r in spec.pop("refs")]
            if spec["title_number"]:
                title, _ = Title.objects.update_or_create(title_number=spec["title_number"], defaults=spec)
            else:
                title = Title.objects.filter(title_number=None, properties__in=linked).first()
                if title:
                    for k, v in spec.items():
                        setattr(title, k, v)
                    title.save()
                else:
                    title = Title.objects.create(**spec)
            title.properties.set(linked)

        self.load_surveyors(refs)
        self.load_photos(refs)
        self.load_documents()
        self.load_inspire(refs)
        from apps.leases import demo as lease_demo

        lease_count = lease_demo.load()
        from apps.ledger import demo as ledger_demo
        from apps.servicecharges import demo as service_demo

        service_demo.setup()
        charge_count = ledger_demo.load()
        from apps.cases import demo as case_demo

        case_count = case_demo.load()
        from apps.maintenance import demo as maintenance_demo

        job_count = maintenance_demo.load()
        from apps.compliance import demo as compliance_demo

        compliance_demo.load()
        from apps.valuations import demo as valuation_demo

        valuation_demo.load()

        modules = ModuleSettings.load()
        if not modules.organisation_name:
            modules.organisation_name = ORG_NAME
            modules.save()

        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded: {created} properties added, {updated} refreshed, {len(TITLES)} titles, "
            f"{lease_count} leases and licences, {charge_count} rent charges, {case_count} cases, "
            f"{job_count} maintenance jobs."
        ))

    def load_surveyors(self, refs):
        User = get_user_model()
        users = {}
        for username, (first, last) in SURVEYORS.items():
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": f"{username}@example.org"},
            )
            if created:
                user.set_unusable_password()
                user.save()
            user.groups.add(Group.objects.get(name=SURVEYOR_ROLE))
            users[username] = user
        for ref, prop in refs.items():
            # Use the nearest listed ancestor's surveyor, so units follow their estate.
            node, username = prop, None
            while node is not None and username is None:
                username = ASSIGNMENTS.get(node.reference)
                node = refs.get(node.parent.reference) if node.parent_id else None
            surveyor = users.get(username)
            if prop.managing_surveyor_id != (surveyor.pk if surveyor else None):
                prop.managing_surveyor = surveyor
                prop.save(update_fields=["managing_surveyor", "updated_at"])

    def load_photos(self, refs):
        for ref, photos in PHOTOS.items():
            prop = refs[ref]
            if prop.photos.exists():
                continue  # keep any photos already there
            for i, (caption, style) in enumerate(photos):
                PropertyPhoto.objects.create(
                    property=prop, caption=caption, is_main=(i == 0), order=i, taken_on=date(2026, 9, 1 + i),
                    image=ContentFile(placeholder_photo(caption, style, i), name="demo.png"),
                )

    def load_documents(self):
        for number, docs in DOCUMENTS.items():
            title = Title.objects.get(title_number=number)
            if title.documents.exists():
                continue
            for doc_type, description, doc_date, lines in docs:
                TitleDocument.objects.create(
                    title=title, document_type=doc_type, description=description, document_date=doc_date,
                    file=ContentFile(placeholder_pdf(f"{description} - {number}", lines), name=f"{number}-{doc_type}.pdf"),
                )

    def load_inspire(self, refs):
        """Fictional INSPIRE-style parcels: one per demo site, plus neighbouring land not owned by the council."""
        if InspireParcel.objects.filter(inspire_id__startswith="DEMO-").exists():
            return
        n = 0

        def parcel(geom):
            nonlocal n
            n += 1
            InspireParcel.objects.create(inspire_id=f"DEMO-{n:05d}", geometry=geom, source_file="Demonstration data")

        for ref, prop in refs.items():
            if prop.parent_id or not prop.boundary or ref == "DM-S06":
                continue
            outline = prop.boundary.buffer(1).envelope  # registered extent slightly larger than the drawn boundary
            parcel(MultiPolygon(outline, srid=27700))
        # The former school site is registered as two titles, to show joining parcels into one boundary.
        parcel(rect(300, 800, 80, 100))
        parcel(rect(380, 800, 60, 100))
        # Neighbouring land (not council-owned) so the map looks like a real parcel fabric.
        for dx, dy, w, h in [(0, 200, 160, 120), (160, 200, 160, 120), (320, 0, 120, 190), (-150, 0, 150, 190),
                             (440, 400, 80, 60), (720, 400, 60, 60), (600, 440, 120, 50), (440, 800, 120, 100),
                             (180, 800, 120, 100), (-480, 600, 300, 300)]:
            parcel(rect(dx, dy, w, h))

    def remove_demo_data(self):
        from apps.leases import demo as lease_demo
        from apps.ledger import demo as ledger_demo

        from apps.servicecharges import demo as service_demo

        from apps.cases import demo as case_demo

        from apps.maintenance import demo as maintenance_demo

        maintenance_demo.remove()
        from apps.compliance import demo as compliance_demo

        compliance_demo.remove()
        from apps.valuations import demo as valuation_demo

        valuation_demo.remove()
        case_demo.remove()
        ledger_demo.remove()
        service_demo.remove()
        lease_demo.remove()
        InspireParcel.objects.filter(inspire_id__startswith="DEMO-").delete()
        demo = Property.objects.filter(reference__startswith=PREFIX)
        Title.objects.filter(title_number__startswith=TITLE_PREFIX).delete()
        Title.objects.filter(title_number=None, properties__in=demo).delete()
        removed = 0
        # Delete leaves first, because a property with parts cannot be deleted.
        while True:
            leaves = demo.filter(children__isnull=True)
            ids = list(leaves.values_list("pk", flat=True))
            if not ids:
                break
            for p in Property.objects.filter(pk__in=ids):
                p.delete()
                removed += 1
        get_user_model().objects.filter(username__in=SURVEYORS, auditentry__isnull=True).delete()
        return removed
