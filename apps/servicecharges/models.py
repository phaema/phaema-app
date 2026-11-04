# SPDX-License-Identifier: AGPL-3.0-or-later
"""Service charges: shared costs recovered from tenants.

A schedule is one pool of costs (for example an estate's roads and landscaping) over a set of
properties, with the leases that contribute. Each service charge year has a budget by cost
heading, on-account demands raised with the rent, the actual spending, and a year-end
reconciliation that charges or credits the difference.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.leases.models import Lease
from apps.properties.models import Property

HEADINGS = [
    ("MAN", "Management fee"), ("CLN", "Cleaning"), ("SEC", "Security"), ("REP", "Repairs and maintenance"),
    ("GRN", "Landscaping and grounds"), ("ROAD", "Roads, paths and lighting"), ("UTIL", "Utilities for common parts"),
    ("INS", "Insurance"), ("WASTE", "Waste and recycling"), ("FIRE", "Fire safety and compliance"),
    ("LIFT", "Lifts and plant"), ("SINK", "Reserve or sinking fund"), ("OTH", "Other"),
    ("INC", "Income and credits"),
]


class CostHeading(models.Model):
    code = models.CharField(_("code"), max_length=10, unique=True)
    name = models.CharField(_("name"), max_length=100)
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("cost heading")

    def __str__(self):
        return self.name


def ensure_headings():
    for i, (code, name) in enumerate(HEADINGS):
        CostHeading.objects.get_or_create(code=code, defaults={"name": name, "order": i * 10})


class Schedule(TimeStampedModel):
    class Basis(models.TextChoices):
        AREA = "area", _("Floor area (NIA)")
        FIXED = "fixed", _("Fixed percentages set for each lease")
        EQUAL = "equal", _("Equal shares per unit")

    name = models.CharField(_("name"), max_length=150)
    description = models.TextField(_("description"), blank=True)
    properties = models.ManyToManyField(Property, related_name="service_charge_schedules",
                                        verbose_name=_("properties covered"),
                                        help_text=_("The estate, building or units whose costs are shared. Shares are "
                                                    "worked out over the lettable units within them."))
    basis = models.CharField(_("how costs are shared"), max_length=10, choices=Basis.choices, default=Basis.AREA)
    year_start_month = models.PositiveSmallIntegerField(_("year starts: month"), default=4)
    year_start_day = models.PositiveSmallIntegerField(_("year starts: day"), default=1)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("service charge schedule")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("servicecharges:schedule", args=[self.pk])

    def clean(self):
        try:
            date(2025, self.year_start_month, self.year_start_day)
        except (ValueError, TypeError):
            raise ValidationError({"year_start_day": _("That is not a valid date.")})


class ScheduleMember(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="members")
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="service_charge_memberships",
                              limit_choices_to={"direction": "out"})
    fixed_percentage = models.DecimalField(_("fixed share (%)"), max_digits=7, decimal_places=4, null=True, blank=True,
                                           help_text=_("Only for schedules shared by fixed percentages."))
    annual_cap = models.DecimalField(_("annual cap (£)"), max_digits=12, decimal_places=2, null=True, blank=True,
                                     help_text=_("If the lease caps the service charge, the most it pays in a year. "
                                                 "The council bears any excess."))
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        ordering = ["lease__reference"]
        constraints = [models.UniqueConstraint(fields=["schedule", "lease"], name="sc_one_membership")]
        verbose_name = _("contributing lease")

    def __str__(self):
        return f"{self.lease} in {self.schedule}"


class ScheduleYear(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Budget being prepared")
        APPROVED = "approved", _("Budget approved: charging on account")
        RECONCILED = "reconciled", _("Reconciled")

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="years")
    start = models.DateField(_("year start"))
    end = models.DateField(_("year end"))
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.DRAFT)
    budget_approved_on = models.DateField(_("budget approved"), null=True, blank=True)
    budget_commentary = models.TextField(
        _("budget commentary"), blank=True,
        help_text=_("Explains the budget to tenants: main changes from last year, planned works, contracts. "
                    "Shown on the tenant budget statement."))
    budget_issued_on = models.DateField(
        _("budget issued to tenants"), null=True, blank=True,
        help_text=_("RICS expects the budget to reach tenants at least one month before the year starts."))
    budget_late_reason = models.TextField(
        _("why the budget was late"), blank=True,
        help_text=_("The RICS standard expects tenants to be given a clear explanation if a deadline is missed."))
    reconciled_on = models.DateField(_("reconciled"), null=True, blank=True)
    statements_issued_on = models.DateField(
        _("year-end statements issued"), null=True, blank=True,
        help_text=_("RICS expects year-end statements within four months of the year end."))
    statements_late_reason = models.TextField(_("why the statements were late"), blank=True)
    certified_by = models.CharField(_("certified by"), max_length=150, blank=True,
                                    help_text=_("Who certified the year-end statement."))
    certification_notes = models.TextField(_("certification and review"), blank=True,
                                           help_text=_("For example, the accountant's review or audit of the statement."))
    apportionment = models.JSONField(_("apportionment at reconciliation"), default=dict, blank=True, editable=False)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["schedule__name", "-start"]
        constraints = [models.UniqueConstraint(fields=["schedule", "start"], name="sc_one_year_per_start")]
        verbose_name = _("service charge year")

    def __str__(self):
        return f"{self.schedule.name} {self.label}"

    @property
    def label(self):
        return f"{self.start:%Y}/{self.end:%y}" if self.start.year != self.end.year else f"{self.start:%Y}"

    @property
    def budget_due(self):
        from apps.core.dates import add_months

        return add_months(self.start, -1)

    @property
    def statements_due(self):
        from apps.core.dates import add_months

        return add_months(self.end, 4)

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def get_absolute_url(self):
        return reverse("servicecharges:year", args=[self.pk])

    def clean(self):
        if self.start and self.end and self.end <= self.start:
            raise ValidationError({"end": _("The year must end after it starts.")})


class BudgetLine(models.Model):
    year = models.ForeignKey(ScheduleYear, on_delete=models.CASCADE, related_name="budget_lines")
    heading = models.ForeignKey(CostHeading, on_delete=models.PROTECT, related_name="budget_lines")
    amount = models.DecimalField(_("budget (£, net of VAT)"), max_digits=12, decimal_places=2)
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        ordering = ["heading__order"]
        constraints = [models.UniqueConstraint(fields=["year", "heading"], name="sc_one_budget_line_per_heading")]
        verbose_name = _("budget line")

    def __str__(self):
        return f"{self.heading} £{self.amount}"


class Expenditure(TimeStampedModel):
    class Kind(models.TextChoices):
        COST = "cost", _("Cost")
        INCOME = "income", _("Income or credit (interest, rebate, commission)")

    year = models.ForeignKey(ScheduleYear, on_delete=models.CASCADE, related_name="expenditure")
    heading = models.ForeignKey(CostHeading, on_delete=models.PROTECT, related_name="expenditure")
    spent_on = models.DateField(_("date"))
    supplier = models.CharField(_("supplier"), max_length=150, blank=True)
    description = models.CharField(_("description"), max_length=200)
    invoice_reference = models.CharField(_("invoice or finance reference"), max_length=60, blank=True)
    amount = models.DecimalField(_("amount (£, net of recoverable VAT)"), max_digits=12, decimal_places=2,
                                 help_text=_("A positive amount, for costs and income alike."))
    kind = models.CharField(_("type"), max_length=10, choices=Kind.choices, default=Kind.COST,
                            help_text=_("Income such as interest, rebates and commissions is credited to the "
                                        "service charge and reduces what tenants pay."))
    recoverable = models.BooleanField(
        _("recoverable from tenants"), default=True,
        help_text=_("Untick for costs the council bears itself, such as improvements or costs the leases "
                    "do not allow."))

    class Category(models.TextChoices):
        STANDARD = "", _("Service cost")
        BSA_DEFECT = "bsa_defect", _("Building Safety Act defect (not recoverable)")
        IMPROVEMENT = "improvement", _("Improvement or enhancement")

    category = models.CharField(
        _("category"), max_length=12, choices=Category.choices, blank=True, default="",
        help_text=_("Remedying defects covered by the Building Safety Act 2022 is not recoverable. Improvements are "
                    "recoverable only where tenants have agreed, with a cost-benefit case."))
    improvement_agreed = models.BooleanField(
        _("tenants agreed the improvement, with a cost-benefit case"), default=False)

    class Meta:
        ordering = ["spent_on", "pk"]
        verbose_name = _("expenditure")
        verbose_name_plural = _("expenditure")

    def __str__(self):
        return f"{self.spent_on:%d/%m/%Y} {self.heading} £{self.amount}"

    def clean(self):
        if self.year_id and self.spent_on and not (self.year.start <= self.spent_on <= self.year.end):
            raise ValidationError({"spent_on": _("The date must fall within the service charge year.")})
        if self.category == self.Category.IMPROVEMENT and self.recoverable and not self.improvement_agreed:
            raise ValidationError({"recoverable": _("An improvement is recoverable only where tenants have agreed "
                                                    "it, with a cost-benefit case. Tick that, or untick "
                                                    "recoverable.")})

    def save(self, *args, **kwargs):
        if self.category == self.Category.BSA_DEFECT:
            self.recoverable = False
        super().save(*args, **kwargs)
