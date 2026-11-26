# SPDX-License-Identifier: AGPL-3.0-or-later
"""The property events pipeline: dated property events for the next five financial years.

Drawn entirely from records PHAEMA already holds:
- lease events on agreements, split by which way the agreement runs (council as landlord, council as tenant);
- disposals: expected disposal dates on properties, disposal projects, and properties whose asset strategy
  leads to disposal but which have no expected date yet;
- acquisitions: acquisition projects and their target dates;
- strategy reviews: the date each property's asset strategy is due for review.

Events before today that still need action (a rent review not yet settled, an agreement past its expiry but
not recorded as ended, a disposal or acquisition that has slipped, a review overdue) are shown as overdue. Past
break dates, notice deadlines and option dates are left out: they have lapsed.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from apps.projects.models import financial_year_label, financial_year_of

YEARS = 5

SECTIONS = [
    ("landlord", "Council as landlord: lease events",
     "Agreements the council has let out. Breaks and expiries here are a risk to income; reviews a chance to "
     "raise it."),
    ("tenant", "Council as tenant: lease events",
     "Agreements under which the council holds property. Each break, expiry and option is a decision to stay, "
     "move or leave."),
    ("disposals", "Disposals",
     "Properties expected to be sold or let on a long lease, and disposal projects. Values are expected "
     "receipts."),
    ("acquisitions", "Acquisitions",
     "Acquisition projects. Values are the forecast cost, where you can see the budget."),
    ("reviews", "Strategy reviews due",
     "Properties whose asset strategy is due for review: the rolling Asset Challenge programme."),
]
SECTION_TITLES = {key: title for key, title, _note in SECTIONS}
VALUE_LABELS = {"landlord": "Rent received", "tenant": "Rent paid", "disposals": "Expected receipts",
                "acquisitions": "Forecast cost", "reviews": ""}
SHEETS = {"landlord": "Council as landlord", "tenant": "Council as tenant", "disposals": "Disposals",
          "acquisitions": "Acquisitions", "reviews": "Strategy reviews"}
LEASE_KINDS = {"review": "Rent review", "break": "Break", "notice": "Last date for break notice",
               "option": "Option", "expiry": "Expiry"}
LIVE_LEASES = ("current", "holding_over")
OPEN_PROJECTS = ("active", "paused")


@dataclass
class Event:
    section: str
    day: date | None
    what: str
    place: str = ""
    place_url: str = ""
    record: str = ""
    record_url: str = ""
    value: Decimal | None = None
    note: str = ""
    bucket: object = None  # "overdue", a financial year (int), or "nodate"


@dataclass
class Pipeline:
    today: date
    years: list
    portfolio: object = None
    events: dict = field(default_factory=dict)  # section -> [Event], in date order
    beyond: dict = field(default_factory=dict)  # section -> count of events after the five years

    def buckets(self):
        """Every column of the summary, in order: overdue, each year, no date."""
        return ["overdue", *self.years, "nodate"]

    def bucket_label(self, bucket):
        if bucket == "overdue":
            return "Overdue"
        if bucket == "nodate":
            return "No date yet"
        return financial_year_label(bucket)

    def grouped(self, section):
        """[(bucket label, [Event])] for one section, leaving out empty buckets."""
        found = defaultdict(list)
        for e in self.events.get(section, []):
            found[e.bucket].append(e)
        return [(self.bucket_label(b), found[b]) for b in self.buckets() if found.get(b)]

    def summary(self):
        """Rows of the key figures table: (title, counts by bucket, total count, values by bucket, value label)."""
        rows = []
        for key, title, _note in SECTIONS:
            counts, values = [], []
            for b in self.buckets():
                found = [e for e in self.events.get(key, []) if e.bucket == b]
                counts.append(len(found))
                known = [e.value for e in found if e.value is not None]
                values.append(sum(known, Decimal(0)) if known else None)
            rows.append({"key": key, "title": title, "counts": counts, "total": sum(counts), "values": values,
                         "value_label": VALUE_LABELS[key], "beyond": self.beyond.get(key, 0)})
        return rows

    @property
    def total(self):
        return sum(len(v) for v in self.events.values())


def _place(properties):
    """A label and link for the properties an event is about."""
    props = list(properties)
    if not props:
        return "", ""
    first = props[0]
    label = str(first) + (f" and {len(props) - 1} more" if len(props) > 1 else "")
    return label, first.get_absolute_url()


def _bucket(day, today, years):
    if day is None:
        return "nodate"
    if day < today:
        return "overdue"
    fy = financial_year_of(day)
    return fy if fy in years else None


def _lease_events(today, portfolio):
    from apps.leases.models import Lease

    leases = (Lease.objects.filter(status__in=LIVE_LEASES)
              .select_related("counterparty").prefetch_related("properties", "breaks", "options"))
    if portfolio is not None:
        leases = leases.filter(properties__portfolio=portfolio).distinct()
    for lease in leases:
        section = "tenant" if lease.direction == Lease.Direction.IN else "landlord"
        place, place_url = _place(lease.properties.all())
        record = f"{lease.reference} {lease.counterparty}"
        for day, label, kind in lease.key_dates(today):
            if kind not in LEASE_KINDS:
                continue
            past = day < today
            note = ""
            if past and kind == "review":
                note = "Review date passed; not yet settled"
            elif past and kind == "expiry":
                note = "Past expiry; agreement not recorded as ended"
            elif past:
                continue  # a lapsed break, notice or option date
            if kind == "review" and lease.time_of_essence:
                note = "; ".join(x for x in (note, "Time is of the essence") if x)
            yield Event(section, day, str(label), place, place_url, record, lease.get_absolute_url(),
                        lease.annual_rent, note)


def _project_value(project, user, income):
    """The project's forecast receipts (income lines) or cost (other lines), if this person may see the budget."""
    from apps.projects import rules
    from apps.projects.models import BudgetLine, BudgetYear

    if user is not None and not rules.can_see_budget(user, project):
        return None
    years = BudgetYear.objects.filter(line__project=project)
    years = (years.filter(line__category=BudgetLine.Category.INCOME) if income
             else years.exclude(line__category=BudgetLine.Category.INCOME))
    total = years.aggregate(t=Sum("forecast"))["t"]
    return total or None


def _projects(kind, user, portfolio):
    from apps.projects import rules
    from apps.projects.models import Project

    qs = Project.objects.filter(project_type__kind=kind, status__in=OPEN_PROJECTS).prefetch_related(
        "property_links__property")
    if portfolio is not None:
        qs = qs.filter(property_links__property__portfolio=portfolio).distinct()
    if user is not None:
        qs = rules.visible(user, qs)
    return qs


def _project_event(section, project, user, income):
    props = [link.property for link in project.property_links.all()]
    place, place_url = _place(props)
    if not place and project.site_address:
        place = " ".join(project.site_address.split())[:80]
    note = project.get_phase_display()
    if project.status == "paused":
        note += "; paused"
    return Event(section, project.target_date, f"Project: {project.name}", place, place_url,
                 project.display_reference, project.get_absolute_url(), _project_value(project, user, income), note)


def _disposals(today, user, portfolio):
    from apps.properties.models import Property
    from apps.properties.strategy import effective_strategies

    live = Property.objects.filter(disposed_on__isnull=True)
    if portfolio is not None:
        live = live.filter(portfolio=portfolio)
    projects = list(_projects("disposal", user, portfolio))
    # A property in a disposal project is counted once, under the project, so receipts are not added twice.
    in_projects = {link.property_id for p in projects for link in p.property_links.all()}
    for prop in live.filter(disposal_expected_on__isnull=False).exclude(pk__in=in_projects):
        note = prop.get_disposal_method_display() if prop.disposal_method else ""
        yield Event("disposals", prop.disposal_expected_on, "Expected disposal", str(prop), prop.get_absolute_url(),
                    value=prop.disposal_expected_value, note=note)
    # Properties whose asset strategy leads to disposal but with no expected date: the pipeline's unknowns.
    effective = effective_strategies()
    for prop in live.filter(disposal_expected_on__isnull=True).exclude(pk__in=in_projects):
        found = effective.get(prop.pk)
        if not found:
            continue
        decision, own = found
        if own and decision.strategy.follow_on == "disposal":
            yield Event("disposals", None, f"Asset strategy: {decision.strategy}", str(prop),
                        prop.get_absolute_url(), value=prop.disposal_expected_value,
                        note=f"Decided {decision.decided_on:%d %b %Y}; no expected disposal date")
    for project in projects:
        yield _project_event("disposals", project, user, income=True)


def _acquisitions(user, portfolio):
    for project in _projects("acquisition", user, portfolio):
        yield _project_event("acquisitions", project, user, income=False)


def _reviews(portfolio):
    from apps.properties.models import Property
    from apps.properties.strategy import effective_strategies

    live = Property.objects.filter(disposed_on__isnull=True, purpose_review_date__isnull=False)
    if portfolio is not None:
        live = live.filter(portfolio=portfolio)
    effective = effective_strategies()
    for prop in live:
        found = effective.get(prop.pk)
        note = f"Current strategy: {found[0].strategy}" if found else "No asset strategy recorded"
        yield Event("reviews", prop.purpose_review_date, "Strategy review", str(prop), prop.get_absolute_url(),
                    note=note)


def build(user=None, today=None, portfolio=None):
    today = today or date.today()
    first = financial_year_of(today)
    years = list(range(first, first + YEARS))
    pipe = Pipeline(today=today, years=years, portfolio=portfolio)
    found = defaultdict(list)
    sources = [_lease_events(today, portfolio), _disposals(today, user, portfolio), _acquisitions(user, portfolio),
               _reviews(portfolio)]
    for source in sources:
        for event in source:
            event.bucket = _bucket(event.day, today, years)
            if event.bucket is None:
                pipe.beyond[event.section] = pipe.beyond.get(event.section, 0) + 1
                continue
            found[event.section].append(event)
    for key, _title, _note in SECTIONS:
        pipe.events[key] = sorted(found.get(key, []), key=lambda e: (e.day is None, e.day or today, e.place))
    return pipe


def _money(value):
    return f"£{value:,.0f}" if value is not None else ""


def to_markup(pipe, user=None):
    """The pipeline in the document library's markup, for the Word download."""
    from apps.properties.report import _date, _head, _name, _row

    scope = f" for the {pipe.portfolio} portfolio" if pipe.portfolio else ""
    out = [f"# Property events pipeline{scope}", "",
           f"Prepared {_date(pipe.today)}" + (f" by {_name(user)}" if user else "") +
           f". Financial years {pipe.bucket_label(pipe.years[0])} to {pipe.bucket_label(pipe.years[-1])}, "
           "with anything overdue first.", "",
           "# Key figures", "",
           _head("", *(pipe.bucket_label(b) for b in pipe.buckets()), "Total")]
    for row in pipe.summary():
        out.append(_row(row["title"], *(str(n) for n in row["counts"]), str(row["total"])))
        if row["value_label"]:
            out.append(_row(f"{row['value_label']} (£)", *(_money(v) for v in row["values"]), ""))
    out.append("")
    for key, title, note in SECTIONS:
        out += [f"# {title}", "", note, ""]
        groups = pipe.grouped(key)
        if not groups:
            out += ["Nothing in the next five years.", ""]
        for label, events in groups:
            out += [f"## {label}", "", _head("Date", "Event", "Property", "Record", VALUE_LABELS[key] or "Notes",
                                             *(["Notes"] if VALUE_LABELS[key] else []))]
            for e in events:
                cells = [_date(e.day) or "Not set", e.what, e.place, e.record]
                cells += [_money(e.value), e.note] if VALUE_LABELS[key] else [e.note]
                out.append(_row(*cells))
            out.append("")
        if pipe.beyond.get(key):
            out += [f"A further {pipe.beyond[key]} after {pipe.bucket_label(pipe.years[-1])}.", ""]
    return "\n".join(out)


def to_xlsx(pipe):
    """The pipeline as a spreadsheet: a key figures sheet and one sheet of events per section."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Key figures"
    bold = Font(bold=True)
    ws.append(["Property events pipeline" + (f": {pipe.portfolio}" if pipe.portfolio else "")])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Prepared {pipe.today:%d %B %Y}"])
    ws.append([])
    ws.append(["", *(pipe.bucket_label(b) for b in pipe.buckets()), "Total", "After five years"])
    for c in ws[ws.max_row]:
        c.font = bold
    for row in pipe.summary():
        ws.append([row["title"], *row["counts"], row["total"], row["beyond"]])
        if row["value_label"]:
            ws.append([f"{row['value_label']} (£)", *(float(v) if v is not None else None for v in row["values"])])
            for c in ws[ws.max_row][1:]:
                c.number_format = "£#,##0"
    ws.column_dimensions["A"].width = 38
    for key, _title, _note in SECTIONS:
        sheet = wb.create_sheet(SHEETS[key])
        sheet.append(["Period", "Date", "Event", "Property", "Record", VALUE_LABELS[key] or "Value", "Notes"])
        for c in sheet[1]:
            c.font = bold
        for e in pipe.events.get(key, []):
            sheet.append([pipe.bucket_label(e.bucket), e.day, e.what, e.place, e.record,
                          float(e.value) if e.value is not None else None, e.note])
            sheet.cell(sheet.max_row, 2).number_format = "d mmm yyyy"
            sheet.cell(sheet.max_row, 6).number_format = "£#,##0"
        for col, width in zip("ABCDEFG", (12, 14, 34, 40, 30, 16, 40)):
            sheet.column_dimensions[col].width = width
        sheet.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
