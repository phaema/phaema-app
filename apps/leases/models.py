# SPDX-License-Identifier: AGPL-3.0-or-later
"""Leases, licences and other occupational agreements, and the parties to them."""
from datetime import date, timedelta

import uuid

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.files import validate_pdf
from apps.core.models import TimeStampedModel
from apps.properties.models import Property


class Party(TimeStampedModel):
    """A tenant, licensee, landlord, guarantor or other party to an agreement."""

    class PartyType(models.TextChoices):
        COMPANY = "company", _("Company")
        LLP = "llp", _("Limited liability partnership")
        CHARITY = "charity", _("Charity or community group")
        PUBLIC = "public", _("Public body")
        SOLE_TRADER = "sole_trader", _("Sole trader or individual")
        PARTNERSHIP = "partnership", _("Partnership")
        OTHER = "other", _("Other")

    name = models.CharField(_("name"), max_length=200)
    party_type = models.CharField(_("type"), max_length=20, choices=PartyType.choices)
    company_number = models.CharField(_("company number"), max_length=10, blank=True)
    charity_number = models.CharField(_("charity number"), max_length=12, blank=True)
    contact_name = models.CharField(_("contact name"), max_length=200, blank=True)
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    address = models.TextField(_("correspondence address"), blank=True)
    finance_customer_ref = models.CharField(
        _("finance system customer number"), max_length=30, blank=True,
        help_text=_("The debtor or customer reference in the council's finance system."),
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("party")
        verbose_name_plural = _("parties")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("leases:party", args=[self.pk])

    def arrangements(self):
        """Every agreement this party is involved in, with its role, newest first within status."""
        rows = []
        qs = Lease.objects.filter(models.Q(counterparty=self) | models.Q(guarantor=self)).distinct()
        for lease in qs.select_related("counterparty").prefetch_related("properties").order_by("status", "-term_start"):
            if lease.guarantor_id == self.pk and lease.counterparty_id != self.pk:
                role = _("Guarantor")
            elif lease.direction == Lease.Direction.IN:
                role = _("Landlord")
            else:
                role = _("Tenant") if lease.agreement_type != Lease.AgreementType.LICENCE else _("Licensee")
            rows.append({"lease": lease, "role": role, "properties": list(lease.properties.all())})
        return rows

    def properties_involved(self):
        """Distinct properties across all of this party's agreements."""
        seen = {}
        for row in self.arrangements():
            for p in row["properties"]:
                seen.setdefault(p.pk, p)
        return sorted(seen.values(), key=lambda p: p.reference)


class Lease(TimeStampedModel):
    """A lease, licence or other agreement under which land or property is occupied."""

    class Direction(models.TextChoices):
        OUT = "out", _("Let out by the council (council is landlord)")
        IN = "in", _("Held by the council (council is tenant)")

    class AgreementType(models.TextChoices):
        LEASE = "lease", _("Lease")
        LICENCE = "licence", _("Licence")
        TENANCY_AT_WILL = "taw", _("Tenancy at will")
        AGREEMENT_FOR_LEASE = "afl", _("Agreement for lease")
        FBT = "fbt", _("Farm business tenancy")
        WAYLEAVE = "wayleave", _("Wayleave")
        EASEMENT = "easement", _("Easement")
        CONCESSION = "concession", _("Concession")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        PROPOSED = "proposed", _("Proposed (heads of terms)")
        CURRENT = "current", _("Current")
        HOLDING_OVER = "holding_over", _("Holding over")
        ENDED = "ended", _("Ended")

    class Security(models.TextChoices):
        INSIDE = "inside", _("Inside the 1954 Act (security of tenure)")
        CONTRACTED_OUT = "contracted_out", _("Contracted out of the 1954 Act")
        NOT_APPLICABLE = "na", _("Not applicable")
        UNKNOWN = "unknown", _("Not known")

    class RentFrequency(models.TextChoices):
        QUARTER_DAYS = "quarter_days", _("Quarterly in advance (usual quarter days)")
        QUARTERLY = "quarterly", _("Quarterly in advance (other dates)")
        MONTHLY = "monthly", _("Monthly in advance")
        ANNUALLY = "annually", _("Annually in advance")
        PEPPERCORN = "peppercorn", _("Peppercorn / no rent")

    class ReviewBasis(models.TextChoices):
        OPEN_MARKET_UPWARDS = "om_up", _("Open market, upwards only")
        OPEN_MARKET = "om", _("Open market, upwards or downwards")
        RPI = "rpi", _("RPI linked")
        CPI = "cpi", _("CPI linked")
        FIXED = "fixed", _("Fixed increases")
        TURNOVER = "turnover", _("Turnover")
        NONE = "none", _("No reviews")

    class Repairing(models.TextChoices):
        FRI = "fri", _("Full repairing and insuring")
        IRI = "iri", _("Internal repairing and insuring")
        LIMITED = "limited", _("Limited by schedule of condition")
        LANDLORD = "landlord", _("Landlord repairs")
        OTHER = "other", _("Other (see notes)")

    class Insurance(models.TextChoices):
        LANDLORD_RECHARGED = "landlord_recharged", _("Landlord insures and recharges")
        LANDLORD = "landlord", _("Landlord insures, not recharged")
        TENANT = "tenant", _("Tenant insures")

    reference = models.CharField(_("reference"), max_length=30, unique=True)
    direction = models.CharField(_("direction"), max_length=3, choices=Direction.choices, default=Direction.OUT)
    agreement_type = models.CharField(_("agreement type"), max_length=20, choices=AgreementType.choices)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.CURRENT)
    properties = models.ManyToManyField(Property, related_name="leases", verbose_name=_("premises"))
    premises_description = models.CharField(
        _("premises description"), max_length=255, blank=True,
        help_text=_("As described in the lease, e.g. 'Ground floor shop and rear yard'."),
    )
    counterparty = models.ForeignKey(
        Party, verbose_name=_("tenant or landlord"), on_delete=models.PROTECT, related_name="leases",
        help_text=_("The tenant or licensee for agreements let out; the landlord for agreements held."),
    )
    guarantor = models.ForeignKey(
        Party, verbose_name=_("guarantor"), null=True, blank=True, on_delete=models.PROTECT, related_name="guarantees"
    )

    # Dates
    lease_date = models.DateField(_("date of agreement"), null=True, blank=True)
    term_start = models.DateField(_("term start"))
    term_end = models.DateField(_("contractual expiry"), null=True, blank=True,
                                help_text=_("Leave blank for periodic or rolling agreements."))
    actual_end = models.DateField(_("date ended"), null=True, blank=True,
                                  help_text=_("When the agreement actually ended (surrender, forfeiture, expiry)."))
    security_of_tenure = models.CharField(_("security of tenure"), max_length=20, choices=Security.choices,
                                          default=Security.UNKNOWN)

    # Rent
    annual_rent = models.DecimalField(_("current annual rent (£)"), max_digits=12, decimal_places=2,
                                      default=0, validators=[MinValueValidator(0)])
    rent_frequency = models.CharField(_("rent payable"), max_length=20, choices=RentFrequency.choices,
                                      default=RentFrequency.QUARTER_DAYS)
    vat_chargeable = models.BooleanField(_("VAT charged on rent"), default=False,
                                         help_text=_("Tick if the council has opted to tax and charges VAT."))
    deposit = models.DecimalField(_("rent deposit (£)"), max_digits=12, decimal_places=2, null=True, blank=True)
    deposit_held = models.CharField(_("deposit held"), max_length=200, blank=True,
                                    help_text=_("Where the deposit is held, for example the deposit account and the "
                                                "deed's date."))
    deposit_interest = models.CharField(_("interest on the deposit"), max_length=200, blank=True,
                                        help_text=_("Who it belongs to and when it is paid, for example \"to the "
                                                    "tenant, yearly, at base rate\"."))
    rates_excluded = models.BooleanField(_("rent excludes business rates"), default=True,
                                         help_text=_("Untick if the rent includes business rates."))
    incentives = models.TextField(_("rent-free period or other incentive"), blank=True)

    # Reviews
    review_basis = models.CharField(_("rent review basis"), max_length=20, choices=ReviewBasis.choices,
                                    default=ReviewBasis.NONE)
    review_interval_years = models.PositiveSmallIntegerField(_("review every (years)"), null=True, blank=True)
    next_review_date = models.DateField(_("next rent review"), null=True, blank=True)

    # Terms
    repairing = models.CharField(_("repairing obligation"), max_length=20, choices=Repairing.choices, blank=True)
    insurance = models.CharField(_("insurance"), max_length=20, choices=Insurance.choices, blank=True)
    service_charge_payable = models.BooleanField(_("service charge payable"), default=False)
    permitted_use = models.CharField(_("permitted use"), max_length=255, blank=True)
    alienation = models.TextField(_("assignment and subletting"), blank=True)
    alterations = models.TextField(_("alterations and reinstatement"), blank=True)
    special_rights = models.TextField(_("special rights"), blank=True,
                                      help_text=_("For example parking spaces, rights of way, telecoms access."))
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["reference"]
        verbose_name = _("lease or licence")
        verbose_name_plural = _("leases and licences")

    def __str__(self):
        return f"{self.reference} {self.counterparty}"

    def get_absolute_url(self):
        return reverse("leases:detail", args=[self.pk])

    def clean(self):
        super().clean()
        if self.term_end and self.term_start and self.term_end < self.term_start:
            raise ValidationError({"term_end": _("The expiry date must be after the term start.")})
        if self.guarantor_id and self.guarantor_id == self.counterparty_id:
            raise ValidationError({"guarantor": _("The guarantor cannot be the same party as the tenant.")})
        if self.next_review_date and self.review_basis == self.ReviewBasis.NONE:
            raise ValidationError({"review_basis": _("Choose a review basis, or remove the next review date.")})

    @property
    def is_let_out(self):
        return self.direction == self.Direction.OUT

    @property
    def term_description(self):
        """Length of the term, e.g. a lease from 25 March 2020 to 24 March 2030 is "10 years"."""
        if not self.term_end:
            return _("Periodic / no fixed expiry")
        end = self.term_end + timedelta(days=1)
        months = (end.year - self.term_start.year) * 12 + end.month - self.term_start.month
        if end.day < self.term_start.day:
            months -= 1
        years, rem = divmod(max(months, 0), 12)
        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if rem:
            parts.append(f"{rem} month{'s' if rem != 1 else ''}")
        return " ".join(parts) or _("Less than a month")

    def key_dates(self, today=None):
        """Upcoming and recent key dates, sorted, as (date, label, kind) tuples."""
        today = today or date.today()
        dates = []
        if self.next_review_date:
            dates.append((self.next_review_date, _("Rent review"), "review"))
        for b in self.breaks.all():
            who = b.get_exercisable_by_display().lower()
            dates.append((b.break_date, _("Break option (%(who)s)") % {"who": who}, "break"))
            if b.notice_deadline:
                dates.append((b.notice_deadline, _("Last date to serve break notice (%(who)s)") % {"who": who}, "notice"))
        if self.term_end:
            dates.append((self.term_end, _("Contractual expiry"), "expiry"))
        return sorted(dates, key=lambda d: d[0])


class BreakOption(TimeStampedModel):
    class ExercisableBy(models.TextChoices):
        TENANT = "tenant", _("Tenant only")
        LANDLORD = "landlord", _("Landlord only")
        EITHER = "either", _("Either party")

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="breaks")
    break_date = models.DateField(_("break date"))
    exercisable_by = models.CharField(_("exercisable by"), max_length=10, choices=ExercisableBy.choices)
    notice_months = models.PositiveSmallIntegerField(_("notice (months)"), null=True, blank=True)
    conditions = models.TextField(_("conditions"), blank=True,
                                  help_text=_("e.g. rent paid up to date, vacant possession."))

    class Meta:
        ordering = ["break_date"]
        verbose_name = _("break option")
        verbose_name_plural = _("break options")

    def __str__(self):
        return f"Break {self.break_date:%d %b %Y} ({self.get_exercisable_by_display()})"

    def get_absolute_url(self):
        return self.lease.get_absolute_url()

    @property
    def notice_deadline(self):
        if not self.notice_months:
            return None
        year, month = self.break_date.year, self.break_date.month - self.notice_months
        while month < 1:
            month += 12
            year -= 1
        from calendar import monthrange

        day = min(self.break_date.day, monthrange(year, month)[1])
        return date(year, month, day)


def _lease_document_path(instance, filename):
    return f"leases/{instance.lease_id}/{uuid.uuid4().hex}.pdf"


class LeaseDocument(TimeStampedModel):
    """A PDF held against an agreement: the lease itself, licences, variations, memoranda and notices."""

    class DocumentType(models.TextChoices):
        LEASE = "lease", _("Lease or licence (signed copy)")
        COUNTERPART = "counterpart", _("Counterpart")
        VARIATION = "variation", _("Deed of variation")
        LICENCE_ASSIGN = "licence_assign", _("Licence to assign or underlet")
        LICENCE_ALTER = "licence_alter", _("Licence for alterations")
        RENT_REVIEW = "rent_review", _("Rent review memorandum")
        SCHEDULE = "schedule", _("Schedule of condition")
        NOTICE = "notice", _("Notice (e.g. section 25 or 26, break)")
        HEADS_OF_TERMS = "heads", _("Heads of terms")
        OTHER = "other", _("Other document")

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(_("document type"), max_length=20, choices=DocumentType.choices)
    file = models.FileField(_("PDF file"), upload_to=_lease_document_path, validators=[validate_pdf],
                            help_text=_("PDF up to 25 MB."))
    original_filename = models.CharField(_("original file name"), max_length=255, blank=True, editable=False)
    description = models.CharField(_("description"), max_length=200, blank=True)
    document_date = models.DateField(_("document date"), null=True, blank=True)

    class Meta:
        ordering = ["document_type", "-document_date"]
        verbose_name = _("lease document")
        verbose_name_plural = _("lease documents")

    def __str__(self):
        return self.description or self.get_document_type_display()

    def get_absolute_url(self):
        return self.lease.get_absolute_url()

    def save(self, *args, **kwargs):
        if self.file and not getattr(self.file, "_committed", True):
            self.original_filename = self.file.name.rsplit("/", 1)[-1][:255]
        super().save(*args, **kwargs)


class RentScheduleEntry(TimeStampedModel):
    """The rent payable from a date: the initial rent, review outcomes, fixed steps and variations.

    The lease's current annual rent is always the entry in force today; future entries
    (stepped rents) take effect automatically on their date.
    """

    class Reason(models.TextChoices):
        INITIAL = "initial", _("Initial rent")
        REVIEW = "review", _("Rent review")
        STEP = "step", _("Fixed step")
        INDEXATION = "index", _("Index-linked increase")
        VARIATION = "variation", _("Variation or concession")
        RENEWAL = "renewal", _("Lease renewal")

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="rent_schedule")
    effective_from = models.DateField(_("effective from"))
    annual_rent = models.DecimalField(_("annual rent (£)"), max_digits=12, decimal_places=2,
                                      validators=[MinValueValidator(0)])
    reason = models.CharField(_("reason"), max_length=20, choices=Reason.choices)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["lease", "effective_from"]
        constraints = [models.UniqueConstraint(fields=["lease", "effective_from"], name="one_rent_per_date")]
        verbose_name = _("rent schedule entry")
        verbose_name_plural = _("rent schedule")

    def __str__(self):
        return f"£{self.annual_rent:,.2f} from {self.effective_from:%d %b %Y}"

    def get_absolute_url(self):
        return self.lease.get_absolute_url()


class LeaseEvent(TimeStampedModel):
    """Something that must be done by a date: generated from the lease, or added by hand."""

    class EventType(models.TextChoices):
        REVIEW = "review", _("Rent review")
        BREAK_NOTICE = "notice", _("Break notice deadline")
        BREAK = "break", _("Break date")
        EXPIRY = "expiry", _("Lease expiry")
        OTHER = "other", _("Other (added by hand)")

    class Status(models.TextChoices):
        OPEN = "open", _("To do")
        IN_PROGRESS = "in_progress", _("In progress")
        DONE = "done", _("Completed")
        LAPSED = "lapsed", _("Lapsed / not used")

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(_("event"), max_length=20, choices=EventType.choices)
    title = models.CharField(_("title"), max_length=200, blank=True)
    due_date = models.DateField(_("due date"), db_index=True)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.OPEN)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("assigned to"), null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="lease_events")
    source = models.CharField(
        max_length=60, blank=True, editable=False,
        help_text=_("What generated this event, e.g. 'review' or 'break:12'. Blank for events added by hand."),
    )
    completed_on = models.DateField(_("completed on"), null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
                                     on_delete=models.SET_NULL, related_name="+")
    outcome = models.TextField(_("outcome and notes"), blank=True)

    class Meta:
        ordering = ["due_date", "pk"]
        verbose_name = _("lease event")
        verbose_name_plural = _("lease events")

    def __str__(self):
        return f"{self.display_title} – {self.lease.reference} ({self.due_date:%d %b %Y})"

    def get_absolute_url(self):
        return reverse("leases:event", args=[self.pk])

    @property
    def display_title(self):
        return self.title or self.get_event_type_display()

    @property
    def is_open(self):
        return self.status in (self.Status.OPEN, self.Status.IN_PROGRESS)

    def days_to_go(self, today=None):
        return (self.due_date - (today or date.today())).days

    def rag(self, today=None):
        """(colour, label) for the status tag."""
        if not self.is_open:
            return ("grey", self.get_status_display())
        days = self.days_to_go(today)
        if days < 0:
            return ("red", _("Overdue"))
        if days <= 90:
            return ("orange", _("Due within 3 months"))
        if days <= 183:
            return ("yellow", _("Due within 6 months"))
        return ("green", _("Later"))


class ReminderLog(models.Model):
    """Which reminders have been sent, so nobody is emailed twice for the same thing."""

    event = models.ForeignKey(LeaseEvent, on_delete=models.CASCADE, related_name="reminders")
    stage = models.CharField(max_length=20)  # e.g. "90" days before, or "overdue-2026-W45"
    sent_to = models.EmailField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "stage", "sent_to"], name="one_reminder_per_stage")]


def _new_token():
    return secrets.token_urlsafe(24)


class CalendarFeed(models.Model):
    """A private web address for a user's lease events, for Outlook or any calendar app."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed")
    token = models.CharField(max_length=64, unique=True, default=_new_token)
    include_all = models.BooleanField(default=False, help_text=_("Include everyone's events, not just mine."))
    created_at = models.DateTimeField(auto_now_add=True)

    def regenerate(self):
        self.token = _new_token()
        self.save(update_fields=["token"])
