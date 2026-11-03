# SPDX-License-Identifier: AGPL-3.0-or-later
"""Case management: every piece of estate work, from a lease event or a request, from start to outcome."""
import builtins
import uuid
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.dates import add_working_days
from apps.core.models import TimeStampedModel
from apps.leases.models import Lease, LeaseEvent, Party
from apps.properties.models import Property


class Stage(models.TextChoices):
    RECEIVED = "received", _("Received")
    INFORMATION = "information", _("Gathering information")
    ASSESSING = "assessing", _("Assessing")
    DECISION = "decision", _("Decision")
    COMPLETING = "completing", _("Completing")


STAGE_ORDER = [s for s, _l in Stage.choices]


class CaseType(models.Model):
    class Group(models.TextChoices):
        CONSENT = "consent", _("Landlord's consents")
        EVENT = "event", _("Lease events")
        MANAGEMENT = "management", _("Lease management")
        INCOME = "income", _("Income recovery")
        VALUATION = "valuation", _("Asset valuation")
        ENQUIRY = "enquiry", _("Land and property enquiries")
        OTHER = "other", _("Other activities")

    code = models.SlugField(_("code"), max_length=40, unique=True)
    name = models.CharField(_("name"), max_length=100)
    group = models.CharField(_("group"), max_length=12, choices=Group.choices, default=Group.OTHER)
    description = models.TextField(_("description"), blank=True)
    target_days = models.PositiveSmallIntegerField(
        _("target days to decision"), null=True, blank=True,
        help_text=_("Calendar days from a complete application to the decision. Blank for no target."))
    acknowledge_working_days = models.PositiveSmallIntegerField(
        _("working days to acknowledge"), default=10, help_text=_("Weekends and bank holidays are not counted."))
    statutory_1988 = models.BooleanField(
        _("Landlord and Tenant Act 1988 applies"), default=False,
        help_text=_("Consent to assign, underlet, charge or part with possession: a decision is due within a "
                    "reasonable time, with written reasons for any conditions or refusal."))
    fee = models.DecimalField(_("fixed fee (£, net)"), max_digits=10, decimal_places=2, null=True, blank=True,
                              help_text=_("The council's fixed fee for this kind of case, charged to the tenant."))
    event_type = models.CharField(_("opened from lease events of type"), max_length=10, blank=True,
                                  choices=LeaseEvent.EventType.choices)
    open_days_before = models.PositiveSmallIntegerField(
        _("open automatically (days before the event)"), null=True, blank=True,
        help_text=_("Leave blank to open cases for this event type only by hand."))
    active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["group", "order", "name"]
        verbose_name = _("case type")

    def __str__(self):
        return self.name


class CaseTypeTask(models.Model):
    case_type = models.ForeignKey(CaseType, on_delete=models.CASCADE, related_name="task_templates")
    stage = models.CharField(_("stage"), max_length=12, choices=Stage.choices)
    description = models.CharField(_("task"), max_length=200)
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("task template")

    def __str__(self):
        return self.description


class Case(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ON_HOLD = "on_hold", _("On hold")
        CLOSED = "closed", _("Closed")

    class Decision(models.TextChoices):
        APPROVED = "approved", _("Approved")
        CONDITIONS = "conditions", _("Approved with conditions")
        REFUSED = "refused", _("Refused")
        WITHDRAWN = "withdrawn", _("Withdrawn")
        NONE = "none", _("No decision needed")

    class Received(models.TextChoices):
        EMAIL = "email", _("Email")
        LETTER = "letter", _("Letter")
        PHONE = "phone", _("Phone")
        ONLINE = "online", _("Online form")
        PERSON = "person", _("In person")
        EVENT = "event", _("PHAEMA lease event")
        OTHER = "other", _("Other")

    year = models.PositiveSmallIntegerField(editable=False)
    number = models.PositiveIntegerField(editable=False)
    case_type = models.ForeignKey(CaseType, on_delete=models.PROTECT, related_name="cases", verbose_name=_("type"))
    title = models.CharField(_("title"), max_length=200)
    stage = models.CharField(_("stage"), max_length=12, choices=Stage.choices, default=Stage.RECEIVED)
    status = models.CharField(_("status"), max_length=8, choices=Status.choices, default=Status.OPEN)
    on_hold_reason = models.CharField(_("on hold because"), max_length=200, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="owned_cases", verbose_name=_("case owner"))
    contributors = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="contributed_cases",
                                          verbose_name=_("contributors"),
                                          help_text=_("For example the legal officer: they can add notes, documents "
                                                      "and correspondence."))
    how_received = models.CharField(_("received by"), max_length=8, choices=Received.choices, default=Received.EMAIL)
    received_on = models.DateField(_("received"), default=date.today,
                                   help_text=_("For consents, the date the written application arrived."))
    acknowledged_on = models.DateField(_("acknowledged"), null=True, blank=True)
    application_complete_on = models.DateField(_("application complete"), null=True, blank=True,
                                               help_text=_("When all the information needed to decide arrived."))
    target_date = models.DateField(_("target decision date"), null=True, blank=True)
    decision = models.CharField(_("decision"), max_length=12, choices=Decision.choices, blank=True)
    decision_on = models.DateField(_("decision sent"), null=True, blank=True)
    reasons = models.TextField(_("reasons and conditions"), blank=True)
    outcome = models.TextField(_("outcome"), blank=True)
    closed_on = models.DateField(_("closed"), null=True, blank=True)
    lease = models.ForeignKey(Lease, on_delete=models.SET_NULL, null=True, blank=True, related_name="cases",
                              verbose_name=_("agreement"))
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="cases",
                                 verbose_name=_("property"))
    party = models.ForeignKey(Party, on_delete=models.SET_NULL, null=True, blank=True, related_name="cases",
                              verbose_name=_("applicant"))
    event = models.ForeignKey(LeaseEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name="cases",
                              verbose_name=_("lease event"))
    applicant_reference = models.CharField(_("applicant's reference"), max_length=60, blank=True)
    iken_matter = models.CharField(_("Iken matter number"), max_length=60, blank=True)
    crm_reference = models.CharField(_("CRM reference"), max_length=60, blank=True)
    fee_charge = models.ForeignKey("ledger.Charge", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="cases", editable=False)

    class Meta:
        ordering = ["-year", "-number"]
        constraints = [models.UniqueConstraint(fields=["year", "number"], name="case_unique_number")]

    def __str__(self):
        return f"{self.display_reference} {self.title}"

    def get_absolute_url(self):
        return reverse("cases:detail", args=[self.pk])

    @builtins.property
    def reference(self):
        return f"CAS-{self.year}-{self.number:04d}" if self.number else "CAS-new"

    @builtins.property
    def main_property(self):
        if self.property_id:
            return self.property
        if self.lease_id:
            return self.lease.properties.first()
        return None

    @builtins.property
    def display_reference(self):
        prop = self.main_property
        return f"{self.reference}/{prop.reference}" if prop else self.reference

    @builtins.property
    def acknowledge_due(self):
        return add_working_days(self.received_on, self.case_type.acknowledge_working_days)

    @builtins.property
    def is_open(self):
        return self.status != self.Status.CLOSED

    def days_left(self, today=None):
        if not self.target_date or self.decision_on or not self.is_open:
            return None
        return (self.target_date - (today or date.today())).days

    def rag(self, today=None):
        if not self.is_open:
            return ("grey", self.get_status_display())
        if self.status == self.Status.ON_HOLD:
            return ("grey", _("On hold"))
        left = self.days_left(today)
        if left is None:
            return ("blue", self.get_stage_display())
        if left < 0:
            return ("red", _("Past target"))
        if left <= 7:
            return ("orange", _("Due within a week"))
        return ("green", _("On track"))

    def refresh_target(self):
        days = self.case_type.target_days
        if days:
            self.target_date = (self.application_complete_on or self.received_on) + timedelta(days=days)
        elif self.event_id and not self.target_date:
            self.target_date = self.event.due_date

    def clean(self):
        if self.decision in (self.Decision.CONDITIONS, self.Decision.REFUSED) and not self.reasons.strip() \
                and self.case_type_id and self.case_type.statutory_1988:
            raise ValidationError({"reasons": _("Give written reasons for conditions or a refusal.")})

    def save(self, *args, **kwargs):
        if not self.number:
            self.year = self.year or (self.received_on or date.today()).year
            with transaction.atomic():
                last = Case.objects.select_for_update().filter(year=self.year).aggregate(n=Max("number"))["n"]
                self.number = (last or 0) + 1
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class CaseTask(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="tasks")
    stage = models.CharField(_("stage"), max_length=12, choices=Stage.choices)
    description = models.CharField(_("task"), max_length=200)
    due_date = models.DateField(_("due"), null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="case_tasks")
    done_on = models.DateField(_("done"), null=True, blank=True)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.description


class CaseNote(TimeStampedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="notes")
    text = models.TextField(_("note"))
    confidential = models.BooleanField(_("confidential"), default=False,
                                       help_text=_("Only the case owner and administrators can see it."))

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:60]


def _case_file_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"cases/{instance.case_id}/{uuid.uuid4().hex}.{ext}"


ALLOWED = {"pdf", "jpg", "jpeg", "png", "eml", "msg", "docx", "xlsx", "doc", "xls", "txt", "csv"}
MAX_BYTES = 25 * 1024 * 1024


def validate_case_file(file):
    name = getattr(file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise ValidationError(_("Upload a PDF, image, email (.eml or .msg), Word, Excel, text or CSV file."))
    if file.size > MAX_BYTES:
        raise ValidationError(_("The file must be smaller than 25 MB."))
    file.seek(0)
    head = file.read(8)
    file.seek(0)
    signatures = {"pdf": [b"%PDF-"], "png": [b"\x89PNG"], "jpg": [b"\xff\xd8"], "jpeg": [b"\xff\xd8"],
                  "docx": [b"PK"], "xlsx": [b"PK"], "doc": [b"\xd0\xcf\x11\xe0"], "xls": [b"\xd0\xcf\x11\xe0"],
                  "msg": [b"\xd0\xcf\x11\xe0"]}
    if ext in signatures and not any(head.startswith(s) for s in signatures[ext]):
        raise ValidationError(_("The file's contents do not match its type."))


class Correspondence(TimeStampedModel):
    class Direction(models.TextChoices):
        IN = "in", _("Received")
        OUT = "out", _("Sent")

    class Method(models.TextChoices):
        EMAIL = "email", _("Email")
        LETTER = "letter", _("Letter")
        PHONE = "phone", _("Phone call")
        MEETING = "meeting", _("Meeting")
        OTHER = "other", _("Other")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="correspondence")
    direction = models.CharField(_("direction"), max_length=3, choices=Direction.choices, default=Direction.IN)
    method = models.CharField(_("method"), max_length=8, choices=Method.choices, default=Method.EMAIL)
    on = models.DateField(_("date"), default=date.today)
    correspondent = models.CharField(_("from or to"), max_length=250, blank=True)
    subject = models.CharField(_("subject"), max_length=250, blank=True)
    summary = models.TextField(_("summary or text"), blank=True)
    file = models.FileField(_("saved email or letter"), upload_to=_case_file_path, blank=True,
                            validators=[validate_case_file])
    original_filename = models.CharField(max_length=255, blank=True, editable=False)

    class Meta:
        ordering = ["-on", "-pk"]
        verbose_name_plural = _("correspondence")

    def __str__(self):
        return self.subject or self.get_method_display()


class CaseDocument(TimeStampedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="documents")
    description = models.CharField(_("description"), max_length=200)
    file = models.FileField(_("file"), upload_to=_case_file_path, validators=[validate_case_file])
    original_filename = models.CharField(max_length=255, blank=True, editable=False)
    correspondence = models.ForeignKey(Correspondence, on_delete=models.CASCADE, null=True, blank=True,
                                       related_name="attachments")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.description
