# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maintenance: contractors and contracts, the component register, planned maintenance and reactive jobs."""
import builtins
import uuid
from datetime import date

from django.conf import settings
from django.db import models, transaction
from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.dates import add_months, add_working_days
from apps.cases.models import validate_case_file
from apps.core.models import TimeStampedModel
from apps.leases.models import Lease
from apps.properties.models import Property


class Category(models.TextChoices):
    STRUCTURE = "structure", _("Structure and frame")
    ROOF = "roof", _("Roof")
    EXTERNAL = "external", _("External walls, windows and doors")
    INTERNAL = "internal", _("Internal finishes and fittings")
    MECHANICAL = "mechanical", _("Heating, ventilation and plumbing")
    ELECTRICAL = "electrical", _("Electrical and lighting")
    FIRE = "fire", _("Fire safety systems")
    LIFT = "lift", _("Lifts and access equipment")
    EXTERNAL_WORKS = "ext_works", _("External works and drainage")
    OTHER = "other", _("Other")


class Responsibility(models.TextChoices):
    LANDLORD = "landlord", _("Council's cost")
    SERVICE_CHARGE = "service", _("Council, recovered through the service charge")
    RECHARGE = "recharge", _("Council, recharged to the tenant")
    TENANT = "tenant", _("Tenant's responsibility")


class Contractor(TimeStampedModel):
    name = models.CharField(_("name"), max_length=200)
    company_number = models.CharField(_("company number"), max_length=10, blank=True)
    trades = models.CharField(_("trades"), max_length=200, blank=True, help_text=_("For example roofing, electrical."))
    contact_name = models.CharField(_("contact name"), max_length=150, blank=True)
    email = models.EmailField(_("email"), blank=True, help_text=_("Works orders are sent here."))
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    emergency_phone = models.CharField(_("out of hours phone"), max_length=30, blank=True)
    address = models.TextField(_("address"), blank=True)
    approved = models.BooleanField(_("on the approved list"), default=True)
    insurer = models.CharField(_("insurer"), max_length=150, blank=True)
    public_liability = models.DecimalField(_("public liability cover (£)"), max_digits=12, decimal_places=0,
                                           null=True, blank=True)
    insurance_expires = models.DateField(_("insurance expires"), null=True, blank=True)
    accreditations = models.TextField(_("accreditations"), blank=True,
                                      help_text=_("For example CHAS, Constructionline, Gas Safe or NICEIC numbers."))
    finance_supplier_ref = models.CharField(_("finance supplier reference"), max_length=40, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("maintenance:contractor", args=[self.pk])

    def insurance_ok(self, on=None):
        return bool(self.insurance_expires and self.insurance_expires >= (on or date.today()))


class Contract(TimeStampedModel):
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT, related_name="contracts",
                                   verbose_name=_("contractor"))
    title = models.CharField(_("title"), max_length=200, help_text=_("For example \"Fire alarm servicing, all sites\"."))
    reference = models.CharField(_("contract reference"), max_length=60, blank=True)
    properties = models.ManyToManyField(Property, blank=True, related_name="contracts", verbose_name=_("properties"))
    starts = models.DateField(_("starts"))
    ends = models.DateField(_("ends"), null=True, blank=True)
    annual_value = models.DecimalField(_("annual value (£)"), max_digits=12, decimal_places=2, null=True, blank=True)
    last_tested = models.DateField(
        _("last tendered or benchmarked"), null=True, blank=True,
        help_text=_("The RICS service charge standard expects contracts to be re-tendered or benchmarked at "
                    "least every three years. Blank means the start date."))
    retender_years = models.PositiveSmallIntegerField(_("re-tender or benchmark every (years)"), default=3)
    service_charge = models.BooleanField(_("recovered through a service charge"), default=False)
    retender_due = models.DateField(_("re-tender or benchmark by"), editable=False, null=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.contractor})"

    def get_absolute_url(self):
        return reverse("maintenance:contracts") + f"#contract-{self.pk}"

    def save(self, *args, **kwargs):
        self.retender_due = add_months(self.last_tested or self.starts, 12 * self.retender_years)
        super().save(*args, **kwargs)


class Component(TimeStampedModel):
    class Condition(models.TextChoices):
        A = "A", _("A: good, performing as intended")
        B = "B", _("B: satisfactory, minor deterioration")
        C = "C", _("C: poor, major repair or replacement soon")
        D = "D", _("D: bad, life expired or serious risk")

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="components",
                                 verbose_name=_("property"))
    name = models.CharField(_("name"), max_length=150, help_text=_("For example \"Gas boiler 1\" or \"Main roof\"."))
    category = models.CharField(_("category"), max_length=12, choices=Category.choices)
    location = models.CharField(_("location"), max_length=150, blank=True)
    uniclass = models.CharField(_("Uniclass 2015 code"), max_length=30, blank=True,
                                help_text=_("For example Ss_60_40_36 for boilers."))
    nrm3 = models.CharField(_("NRM3 element"), max_length=30, blank=True, help_text=_("For example 2.2 for roof."))
    quantity = models.DecimalField(_("quantity"), max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(_("unit"), max_length=10, blank=True, help_text=_("m², m, nr"))
    installed_year = models.PositiveSmallIntegerField(_("installed (year)"), null=True, blank=True)
    life_years = models.PositiveSmallIntegerField(_("expected life (years)"), null=True, blank=True)
    condition = models.CharField(_("condition"), max_length=1, choices=Condition.choices, blank=True)
    condition_on = models.DateField(_("condition assessed"), null=True, blank=True)
    replacement_cost = models.DecimalField(_("replacement cost (£)"), max_digits=12, decimal_places=0,
                                           null=True, blank=True)
    capital = models.BooleanField(_("replacement is capital spending"), default=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["property__reference", "category", "name"]

    def __str__(self):
        return f"{self.name}, {self.property.reference}"

    def get_absolute_url(self):
        return reverse("maintenance:property", args=[self.property_id]) + f"#component-{self.pk}"

    @builtins.property
    def replace_year(self):
        if self.installed_year and self.life_years:
            return self.installed_year + self.life_years
        return None

    def remaining_life(self, year=None):
        if self.replace_year is None:
            return None
        return self.replace_year - (year or date.today().year)


class PlannedTask(TimeStampedModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="planned_tasks",
                                 verbose_name=_("property"))
    component = models.ForeignKey(Component, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="planned_tasks", verbose_name=_("component"))
    title = models.CharField(_("task"), max_length=200)
    category = models.CharField(_("category"), max_length=12, choices=Category.choices, default=Category.OTHER)
    frequency_months = models.PositiveSmallIntegerField(_("every (months)"))
    statutory = models.BooleanField(_("statutory"), default=False,
                                    help_text=_("Required by law: an overdue task shows red everywhere."))
    regulation = models.CharField(_("law or standard"), max_length=200, blank=True)
    contractor = models.ForeignKey(Contractor, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="planned_tasks", verbose_name=_("contractor"))
    contract = models.ForeignKey(Contract, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="planned_tasks", verbose_name=_("contract"))
    last_done = models.DateField(_("last done"), null=True, blank=True)
    next_due = models.DateField(_("next due"))
    estimated_cost = models.DecimalField(_("estimated cost each time (£)"), max_digits=10, decimal_places=2,
                                         null=True, blank=True)
    raise_days_before = models.PositiveSmallIntegerField(
        _("raise a job (days before due)"), null=True, blank=True, default=28,
        help_text=_("PHAEMA raises a job for the contractor this many days ahead. Blank to raise jobs by hand."))
    notes = models.TextField(_("notes"), blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["next_due", "title"]
        verbose_name = _("planned maintenance task")

    def __str__(self):
        return f"{self.title}, {self.property.reference}"

    def get_absolute_url(self):
        return reverse("maintenance:property", args=[self.property_id]) + f"#task-{self.pk}"

    def record_done(self, on):
        self.last_done = on
        self.next_due = add_months(on, self.frequency_months)
        self.save(update_fields=["last_done", "next_due", "updated_at"])

    def rag(self, today=None):
        today = today or date.today()
        if self.next_due < today:
            return ("red", _("Overdue"))
        if (self.next_due - today).days <= 30:
            return ("orange", _("Due soon"))
        return ("green", _("Planned"))


class Job(TimeStampedModel):
    class Priority(models.TextChoices):
        EMERGENCY = "emergency", _("Emergency: make safe within 24 hours")
        URGENT = "urgent", _("Urgent: within 5 working days")
        ROUTINE = "routine", _("Routine: within 20 working days")
        PLANNED = "planned", _("Planned")

    class Status(models.TextChoices):
        REPORTED = "reported", _("Reported")
        ORDERED = "ordered", _("Ordered")
        COMPLETED = "completed", _("Completed")
        CLOSED = "closed", _("Closed")
        CANCELLED = "cancelled", _("Cancelled")

    class Reported(models.TextChoices):
        PHONE = "phone", _("Phone")
        EMAIL = "email", _("Email")
        ONLINE = "online", _("Online form or CRM")
        TENANT = "tenant", _("Tenant")
        INSPECTION = "inspection", _("Inspection")
        PLANNED = "planned", _("Planned maintenance")

    PRIORITY_WORKING_DAYS = {"emergency": None, "urgent": 5, "routine": 20}
    OPEN = ("reported", "ordered")

    year = models.PositiveSmallIntegerField(editable=False)
    number = models.PositiveIntegerField(editable=False)
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="jobs", verbose_name=_("property"))
    component = models.ForeignKey(Component, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs",
                                  verbose_name=_("component"))
    planned_task = models.ForeignKey(PlannedTask, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="jobs", verbose_name=_("planned task"))
    lease = models.ForeignKey(Lease, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs",
                              verbose_name=_("agreement"))
    case = models.ForeignKey("cases.Case", on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs",
                             verbose_name=_("case"))
    title = models.CharField(_("what needs doing"), max_length=200)
    description = models.TextField(_("details"), blank=True)
    category = models.CharField(_("category"), max_length=12, choices=Category.choices, default=Category.OTHER)
    reported_by = models.CharField(_("reported by"), max_length=150, blank=True)
    how_reported = models.CharField(_("how reported"), max_length=10, choices=Reported.choices, default=Reported.PHONE)
    reported_on = models.DateField(_("reported"), default=date.today)
    priority = models.CharField(_("priority"), max_length=10, choices=Priority.choices, default=Priority.ROUTINE)
    target_date = models.DateField(_("target completion"), null=True, blank=True)
    responsibility = models.CharField(_("who pays"), max_length=10, choices=Responsibility.choices,
                                      default=Responsibility.LANDLORD)
    responsibility_reason = models.CharField(_("why"), max_length=200, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.REPORTED)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="maintenance_jobs", verbose_name=_("job owner"))
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT, null=True, blank=True, related_name="jobs",
                                   verbose_name=_("contractor"))
    estimate = models.DecimalField(_("estimate (£, net)"), max_digits=12, decimal_places=2, null=True, blank=True)
    ordered_on = models.DateField(_("order issued"), null=True, blank=True)
    po_number = models.CharField(_("purchase order number"), max_length=40, blank=True)
    completed_on = models.DateField(_("completed"), null=True, blank=True)
    completion_notes = models.TextField(_("work done"), blank=True)
    actual_cost = models.DecimalField(_("final cost (£, net)"), max_digits=12, decimal_places=2, null=True, blank=True)
    invoice_reference = models.CharField(_("contractor's invoice"), max_length=60, blank=True)
    approval_status = models.CharField(_("order approval"), max_length=10, blank=True,
                                       choices=[("pending", _("Waiting")), ("approved", _("Approved")),
                                                ("returned", _("Returned"))])
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="jobs_to_approve", verbose_name=_("approver"))
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="jobs_approved", verbose_name=_("approved by"))
    approved_at = models.DateTimeField(_("approved"), null=True, blank=True)
    approval_comments = models.TextField(_("approver's comments"), blank=True)
    recharge = models.ForeignKey("ledger.Charge", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="jobs", editable=False)
    expenditure = models.ForeignKey("servicecharges.Expenditure", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="jobs", editable=False)

    class Meta:
        ordering = ["-year", "-number"]
        constraints = [models.UniqueConstraint(fields=["year", "number"], name="job_unique_number")]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def get_absolute_url(self):
        return reverse("maintenance:job", args=[self.pk])

    @builtins.property
    def reference(self):
        return f"JOB-{self.year}-{self.number:04d}" if self.number else "JOB-new"

    @builtins.property
    def is_open(self):
        return self.status in self.OPEN

    @builtins.property
    def cost(self):
        return self.actual_cost if self.actual_cost is not None else self.estimate

    def set_target(self):
        days = self.PRIORITY_WORKING_DAYS.get(self.priority)
        if self.priority == self.Priority.EMERGENCY:
            self.target_date = self.reported_on
        elif days:
            self.target_date = add_working_days(self.reported_on, days)

    def rag(self, today=None):
        today = today or date.today()
        if not self.is_open:
            return ("grey", self.get_status_display())
        if self.target_date and self.target_date < today:
            return ("red", _("Past target"))
        if self.priority == self.Priority.EMERGENCY:
            return ("red", _("Emergency"))
        if self.target_date and (self.target_date - today).days <= 2:
            return ("orange", _("Due soon"))
        return ("green", _("On track"))

    def save(self, *args, **kwargs):
        if not self.number:
            with transaction.atomic():
                self.year = self.year or self.reported_on.year
                last = (Job.objects.select_for_update().filter(year=self.year).aggregate(n=Max("number"))["n"]
                        or 0)
                self.number = last + 1
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


def _job_document_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"maintenance/{instance.job_id}/{uuid.uuid4().hex}.{ext}"


class JobDocument(TimeStampedModel):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="documents")
    description = models.CharField(_("description"), max_length=200)
    file = models.FileField(_("file"), upload_to=_job_document_path, validators=[validate_case_file])
    original_filename = models.CharField(_("original file name"), max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.description

