# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compliance certificates, building information (the Golden Thread) and higher-risk screening."""
import builtins
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.cases.models import validate_case_file
from apps.core.dates import add_months
from apps.core.models import TimeStampedModel
from apps.properties.models import Property


class ComplianceType(models.Model):
    code = models.SlugField(_("code"), max_length=40, unique=True)
    name = models.CharField(_("name"), max_length=150)
    valid_months = models.PositiveSmallIntegerField(_("valid for (months)"))
    statutory = models.BooleanField(_("statutory"), default=True)
    regulation = models.CharField(_("law or standard"), max_length=200, blank=True)
    has_rating = models.BooleanField(_("has a rating"), default=False, help_text=_("For example an EPC band."))
    planned_task = models.CharField(_("planned maintenance task"), max_length=40, blank=True,
                                    help_text=_("The library task that produces this certificate, if any."))
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("compliance type")

    def __str__(self):
        return self.name


class Requirement(TimeStampedModel):
    """A certificate this property needs to hold, and who is responsible for it."""

    class Responsible(models.TextChoices):
        COUNCIL = "council", _("Council")
        TENANT = "tenant", _("Tenant (council keeps a copy)")

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="compliance",
                                 verbose_name=_("property"))
    kind = models.ForeignKey(ComplianceType, on_delete=models.PROTECT, related_name="requirements",
                             verbose_name=_("certificate"))
    responsible = models.CharField(_("responsible"), max_length=8, choices=Responsible.choices,
                                   default=Responsible.COUNCIL)
    responsible_reason = models.CharField(_("why"), max_length=200, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["property__reference", "kind__order"]
        constraints = [models.UniqueConstraint(fields=["property", "kind"], name="compliance_one_per_type")]
        verbose_name = _("compliance requirement")

    def __str__(self):
        return f"{self.kind}, {self.property.reference}"

    def get_absolute_url(self):
        return reverse("compliance:property", args=[self.property_id]) + f"#req-{self.pk}"

    @builtins.property
    def latest(self):
        if not hasattr(self, "_latest"):
            self._latest = self.certificates.order_by("-issued_on", "-pk").first()
        return self._latest


def _certificate_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"compliance/{instance.requirement.property_id}/{uuid.uuid4().hex}.{ext}"


class Certificate(TimeStampedModel):
    class Result(models.TextChoices):
        SATISFACTORY = "ok", _("Satisfactory")
        ACTIONS = "actions", _("Satisfactory, with actions")
        UNSATISFACTORY = "fail", _("Unsatisfactory")

    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, related_name="certificates")
    issued_on = models.DateField(_("date of inspection or certificate"))
    expires_on = models.DateField(_("valid until"))
    result = models.CharField(_("result"), max_length=8, choices=Result.choices, default=Result.SATISFACTORY)
    rating = models.CharField(_("rating"), max_length=10, blank=True, help_text=_("For example an EPC band, C."))
    carried_out_by = models.CharField(_("carried out by"), max_length=200, blank=True)
    contractor = models.ForeignKey("maintenance.Contractor", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="certificates", verbose_name=_("contractor"))
    reference = models.CharField(_("certificate number"), max_length=60, blank=True)
    file = models.FileField(_("certificate"), upload_to=_certificate_path, blank=True,
                            validators=[validate_case_file])
    original_filename = models.CharField(max_length=255, blank=True)
    job = models.ForeignKey("maintenance.Job", on_delete=models.SET_NULL, null=True, blank=True,
                            related_name="certificates", verbose_name=_("job"))
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["-issued_on", "-pk"]

    def __str__(self):
        return f"{self.requirement.kind} {self.issued_on:%d/%m/%Y}"

    def get_absolute_url(self):
        return self.requirement.get_absolute_url()

    def save(self, *args, **kwargs):
        if not self.expires_on:
            self.expires_on = add_months(self.issued_on, self.requirement.kind.valid_months)
        super().save(*args, **kwargs)


class Action(TimeStampedModel):
    """Remedial work a certificate or assessment calls for."""

    class Priority(models.TextChoices):
        HIGH = "high", _("High: within 7 days")
        MEDIUM = "medium", _("Medium: within 30 days")
        LOW = "low", _("Low: within 90 days")

    DAYS = {"high": 7, "medium": 30, "low": 90}

    certificate = models.ForeignKey(Certificate, on_delete=models.CASCADE, related_name="actions")
    description = models.CharField(_("action"), max_length=300)
    priority = models.CharField(_("priority"), max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    due_on = models.DateField(_("due"))
    done_on = models.DateField(_("done"), null=True, blank=True)
    job = models.ForeignKey("maintenance.Job", on_delete=models.SET_NULL, null=True, blank=True,
                            related_name="compliance_actions", verbose_name=_("job"))

    class Meta:
        ordering = ["done_on", "due_on"]
        verbose_name = _("remedial action")

    def __str__(self):
        return self.description

    def get_absolute_url(self):
        return self.certificate.get_absolute_url()

    def save(self, *args, **kwargs):
        if not self.due_on:
            self.due_on = self.certificate.issued_on + timedelta(days=self.DAYS.get(self.priority, 30))
        super().save(*args, **kwargs)


class BuildingSafety(TimeStampedModel):
    """Higher-risk screening and the Golden Thread tier for a building."""

    class Country(models.TextChoices):
        ENGLAND = "england", _("England")
        WALES = "wales", _("Wales")

    class Tier(models.TextChoices):
        A = "A", _("A: statutory Golden Thread (higher-risk or in-scope building)")
        B = "B", _("B: best practice (Fire Safety Order buildings)")
        C = "C", _("C: minimal (land and simple assets)")

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="building_safety")
    country = models.CharField(_("country"), max_length=8, choices=Country.choices, default=Country.ENGLAND)
    height_m = models.DecimalField(_("height (metres)"), max_digits=5, decimal_places=1, null=True, blank=True,
                                   help_text=_("Measured as the building regulations describe: ground to the top of "
                                               "the highest occupied floor."))
    storeys = models.PositiveSmallIntegerField(_("storeys"), null=True, blank=True)
    residential_units = models.PositiveSmallIntegerField(_("residential units"), default=0)
    tier = models.CharField(_("Golden Thread tier"), max_length=1, choices=Tier.choices, blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("tier confirmed by"))
    confirmed_on = models.DateField(_("tier confirmed"), null=True, blank=True)
    accountable_person = models.CharField(_("accountable person"), max_length=200, blank=True)
    responsible_person = models.CharField(_("responsible person (Fire Safety Order)"), max_length=200, blank=True)
    notes = models.TextField(_("screening notes"), blank=True)

    class Meta:
        verbose_name = _("building safety screening")
        verbose_name_plural = _("building safety screening")

    def __str__(self):
        return f"Screening, {self.property.reference}"

    def get_absolute_url(self):
        return reverse("compliance:property", args=[self.property_id]) + "#golden-thread"


def _document_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"building-info/{instance.property_id}/{uuid.uuid4().hex}.{ext}"


class BuildingDocument(TimeStampedModel):
    """Building information kept for the life of the building. New versions supersede, never replace."""

    class Category(models.TextChoices):
        PLANS = "plans", _("Plans and drawings")
        FIRE = "fire", _("Fire safety information (regulation 38)")
        HS_FILE = "hs_file", _("Health and safety file (CDM)")
        OM = "om", _("Operation and maintenance manuals")
        SURVEY = "survey", _("Surveys and reports")
        ASBESTOS = "asbestos", _("Asbestos register and plan")
        RISK = "risk", _("Risk assessments")
        CONSENTS = "consents", _("Planning and building control")
        WARRANTY = "warranty", _("Warranties and guarantees")
        OTHER = "other", _("Other")

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="building_documents")
    category = models.CharField(_("category"), max_length=10, choices=Category.choices)
    title = models.CharField(_("title"), max_length=200)
    document_date = models.DateField(_("date of the document"), null=True, blank=True)
    file = models.FileField(_("file"), upload_to=_document_path, validators=[validate_case_file])
    original_filename = models.CharField(max_length=255, blank=True)
    supersedes = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="superseded_by", verbose_name=_("replaces"))
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["category", "title", "-pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("compliance:property", args=[self.property_id]) + f"#doc-{self.pk}"

    @builtins.property
    def is_current(self):
        return not hasattr(self, "superseded_by") or self.superseded_by is None

    def version(self):
        n, node = 1, self
        while node.supersedes_id:
            n, node = n + 1, node.supersedes
        return n
