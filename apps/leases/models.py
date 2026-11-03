# SPDX-License-Identifier: AGPL-3.0-or-later
"""Leases, licences and other occupational agreements, and the parties to them."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

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
