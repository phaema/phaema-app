# SPDX-License-Identifier: AGPL-3.0-or-later
"""Asset valuation for the council's accounts: classes and bases set by finance, valuations with the
records the RICS Red Book expects, the rolling programme (run as cases) and impairment prompts."""
import builtins
import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.cases.models import validate_case_file
from apps.core.models import TimeStampedModel
from apps.properties.models import Property


class Basis(models.TextChoices):
    EUV = "euv", _("Existing use value (EUV)")
    DRC = "drc", _("Depreciated replacement cost (DRC)")
    FV = "fv", _("Fair value")
    FV_LESS_COSTS = "fv_sale", _("Lower of carrying amount and fair value less costs to sell")
    HISTORIC = "historic", _("Historic cost")
    OTHER = "other", _("Other (see notes)")


class AssetClass(models.Model):
    """A class of asset in the council's accounts. Finance sets the basis and how often it is revalued."""

    code = models.SlugField(_("code"), max_length=30, unique=True)
    name = models.CharField(_("name"), max_length=100)
    basis = models.CharField(_("measurement basis"), max_length=10, choices=Basis.choices)
    alternative_basis = models.CharField(
        _("alternative basis"), max_length=10, choices=Basis.choices, blank=True,
        help_text=_("For example DRC for specialised operational buildings with no market evidence."))
    cycle_years = models.PositiveSmallIntegerField(
        _("revalue every (years)"), null=True, blank=True,
        help_text=_("Blank for classes carried at historic cost and not revalued."))
    index = models.CharField(_("index for the years between"), max_length=100, blank=True,
                             help_text=_("For example BCIS for specialised buildings."))
    depreciated = models.BooleanField(_("buildings depreciated"), default=True)
    notes = models.TextField(_("notes"), blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("asset class")
        verbose_name_plural = _("asset classes")

    def __str__(self):
        return self.name

    @builtins.property
    def revalued(self):
        return bool(self.cycle_years)


class ValuationSettings(models.Model):
    """Finance's criteria. One row."""

    year_end_month = models.PositiveSmallIntegerField(_("year end: month"), default=3)
    year_end_day = models.PositiveSmallIntegerField(_("year end: day"), default=31)
    de_minimis = models.DecimalField(
        _("de minimis value (£)"), max_digits=12, decimal_places=0, default=10000,
        help_text=_("Assets worth less than this are not valued in the programme."))
    component_threshold = models.DecimalField(
        _("split into components above (£)"), max_digits=14, decimal_places=0, default=1000000,
        help_text=_("Buildings worth more than this are valued in significant components."))
    component_share = models.PositiveSmallIntegerField(
        _("significant component (% of the building value)"), default=20)
    rotation_years = models.PositiveSmallIntegerField(
        _("rotate the external valuer every (years)"), null=True, blank=True, default=5)
    finance_contact = models.CharField(_("finance contact"), max_length=150, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = _("valuation settings")

    def __str__(self):
        return "Valuation settings"

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def year_end(self, on=None):
        """The next year end on or after `on`."""
        on = on or date.today()
        end = date(on.year, self.year_end_month, self.year_end_day)
        return end if end >= on else date(on.year + 1, self.year_end_month, self.year_end_day)


class Classification(TimeStampedModel):
    """The accounting class of a property from a date. The latest one in force is current."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="classifications")
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT, related_name="classifications",
                                    verbose_name=_("asset class"))
    effective_from = models.DateField(_("from"))
    reason = models.CharField(_("reason"), max_length=200, blank=True,
                              help_text=_("For example: declared surplus by Cabinet, 12 March 2026."))

    class Meta:
        ordering = ["-effective_from", "-pk"]

    def __str__(self):
        return f"{self.property.reference}: {self.asset_class} from {self.effective_from:%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("valuations:property", args=[self.property_id])


class Valuer(TimeStampedModel):
    class Status(models.TextChoices):
        INTERNAL = "internal", _("Internal (council employee)")
        EXTERNAL = "external", _("External")

    name = models.CharField(_("lead valuer"), max_length=150)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="valuer", verbose_name=_("PHAEMA user (internal valuers)"),
                                help_text=_("For a council employee: their valuations appear on their dashboard and "
                                            "they can record them."))
    firm = models.CharField(_("firm"), max_length=150, blank=True)
    status = models.CharField(_("status"), max_length=8, choices=Status.choices, default=Status.EXTERNAL)
    rics_number = models.CharField(_("RICS membership number"), max_length=20, blank=True)
    registered_valuer = models.BooleanField(_("RICS Registered Valuer"), default=True)
    email = models.EmailField(_("email"), blank=True)
    first_instructed = models.DateField(_("first instructed"), null=True, blank=True,
                                        help_text=_("For rotation of the external firm or lead valuer."))
    conflicts = models.TextField(_("conflicts of interest declared"), blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.firm}" if self.firm else self.name

    def rotation_due(self, years, on=None):
        if not years or self.status != self.Status.EXTERNAL or not self.first_instructed:
            return None
        due = date(self.first_instructed.year + years, self.first_instructed.month,
                   min(self.first_instructed.day, 28))
        return due


def _report_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"valuations/{instance.property_id}/{uuid.uuid4().hex}.{ext}"


class Valuation(TimeStampedModel):
    class Status(models.TextChoices):
        INSTRUCTED = "instructed", _("Instructed")
        RECEIVED = "received", _("Received, being reviewed")
        ACCEPTED = "accepted", _("Accepted for the accounts")
        REJECTED = "rejected", _("Returned to the valuer")

    class Method(models.TextChoices):
        COMPARISON = "comparison", _("Comparison")
        INVESTMENT = "investment", _("Investment (income)")
        DRC = "drc", _("Depreciated replacement cost")
        RESIDUAL = "residual", _("Residual")
        PROFITS = "profits", _("Profits")
        OTHER = "other", _("Other")

    class Inspection(models.TextChoices):
        FULL = "full", _("Full internal and external")
        EXTERNAL = "external", _("External only")
        DESKTOP = "desktop", _("Desktop (no inspection)")

    project = models.ForeignKey("projects.Project", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="valuations", verbose_name=_("project"))
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="valuations")
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT, related_name="valuations",
                                    verbose_name=_("asset class"))
    basis = models.CharField(_("basis"), max_length=10, choices=Basis.choices)
    purpose = models.CharField(_("purpose"), max_length=100, default="Financial statements (CIPFA Code)")
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.INSTRUCTED)
    valuer = models.ForeignKey(Valuer, on_delete=models.PROTECT, null=True, blank=True, related_name="valuations",
                               verbose_name=_("valuer"))
    case = models.ForeignKey("cases.Case", on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="valuations", verbose_name=_("case"))
    # Red Book records
    terms_agreed_on = models.DateField(_("terms of engagement agreed"), null=True, blank=True)
    valuation_date = models.DateField(_("valuation date"))
    report_date = models.DateField(_("report date"), null=True, blank=True)
    inspection_date = models.DateField(_("inspected"), null=True, blank=True)
    inspection = models.CharField(_("extent of inspection"), max_length=10, choices=Inspection.choices, blank=True)
    method = models.CharField(_("method"), max_length=12, choices=Method.choices, blank=True)
    special_assumptions = models.TextField(_("special assumptions"), blank=True)
    key_assumptions = models.TextField(_("key assumptions"), blank=True)
    material_uncertainty = models.BooleanField(_("material valuation uncertainty"), default=False)
    uncertainty_statement = models.TextField(_("statement of material uncertainty"), blank=True)
    conflicts = models.TextField(_("conflicts of interest declared"), blank=True)
    # Figures
    value = models.DecimalField(_("value (£)"), max_digits=14, decimal_places=0, null=True, blank=True)
    land_value = models.DecimalField(_("land (£)"), max_digits=14, decimal_places=0, null=True, blank=True)
    building_value = models.DecimalField(_("buildings (£)"), max_digits=14, decimal_places=0, null=True, blank=True)
    remaining_life = models.PositiveSmallIntegerField(_("remaining life of the buildings (years)"), null=True,
                                                      blank=True)
    fair_value_level = models.CharField(
        _("fair value hierarchy level"), max_length=1, blank=True,
        choices=[("1", _("Level 1: quoted prices for identical assets")),
                 ("2", _("Level 2: other observable inputs")), ("3", _("Level 3: unobservable inputs"))],
        help_text=_("For fair value measurements (investment, surplus and held for sale assets), as the accounts "
                    "must disclose."))
    report = models.FileField(_("valuation report"), upload_to=_report_path, blank=True,
                              validators=[validate_case_file])
    # Snapshot of the property when valued, for impairment prompts
    occupation_then = models.CharField(max_length=20, blank=True, editable=False)
    purpose_then = models.CharField(max_length=20, blank=True, editable=False)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", verbose_name=_("accepted by"))
    accepted_on = models.DateField(_("accepted"), null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["-valuation_date", "-pk"]

    def __str__(self):
        return f"{self.property.reference} at {self.valuation_date:%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("valuations:valuation", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.basis and self.asset_class_id:
            self.basis = self.asset_class.basis
        if not self.pk:
            self.occupation_then = self.occupation_then or self.property.occupation or ""
            self.purpose_then = self.purpose_then or self.property.holding_purpose or ""
        super().save(*args, **kwargs)

    def split_ok(self):
        """Land plus buildings should add up to the value."""
        if self.value is None or self.land_value is None or self.building_value is None:
            return True
        return self.land_value + self.building_value == self.value

    def components_total(self):
        return sum((c.value for c in self.components.all()), Decimal("0"))

    def previous(self):
        return (Valuation.objects.filter(property=self.property, status=self.Status.ACCEPTED,
                                         valuation_date__lt=self.valuation_date).first())


class ValuationComponent(models.Model):
    valuation = models.ForeignKey(Valuation, on_delete=models.CASCADE, related_name="components")
    name = models.CharField(_("component"), max_length=150)
    component = models.ForeignKey("maintenance.Component", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="valuation_components")
    value = models.DecimalField(_("value (£)"), max_digits=14, decimal_places=0)
    useful_life = models.PositiveSmallIntegerField(_("remaining useful life (years)"), null=True, blank=True)

    class Meta:
        ordering = ["-value"]

    def __str__(self):
        return self.name


def _audit_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"valuations/audit/{instance.valuation_id}/{uuid.uuid4().hex}.{ext}"


class AuditReview(TimeStampedModel):
    """A valuation selected by the external auditor (or flagged by finance), the council's response, and close-off."""

    class Status(models.TextChoices):
        OPEN = "open", _("Flagged: response being prepared")
        REPORTED = "reported", _("Reported to the auditor")
        CLOSED = "closed", _("Closed")

    class Outcome(models.TextChoices):
        NO_CHANGE = "no_change", _("Auditor satisfied: no change")
        AMENDED = "amended", _("Valuation amended")
        ADJUSTED = "adjusted", _("Accounts adjusted, valuation unchanged")
        OTHER = "other", _("Other (see notes)")

    valuation = models.ForeignKey(Valuation, on_delete=models.CASCADE, related_name="audit_reviews")
    accounts_year = models.CharField(_("accounts"), max_length=20, help_text=_("For example 2026/27."))
    auditor = models.CharField(_("auditor"), max_length=150, blank=True)
    reason = models.CharField(_("why flagged"), max_length=20, default="sample", choices=[
        ("sample", _("Selected in the auditor's sample")), ("query", _("Auditor's query")),
        ("finance", _("Flagged by finance")), ("internal", _("Internal review"))])
    query = models.TextField(_("auditor's query"))
    due_on = models.DateField(_("response due"), null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="audit_reviews", verbose_name=_("preparing the response"))
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.OPEN)
    response = models.TextField(_("the council's response"), blank=True)
    evidence = models.FileField(_("evidence sent"), upload_to=_audit_path, blank=True,
                                validators=[validate_case_file])
    reported_on = models.DateField(_("reported to the auditor"), null=True, blank=True)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    outcome = models.CharField(_("outcome"), max_length=10, choices=Outcome.choices, blank=True)
    closed_on = models.DateField(_("closed"), null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="+")
    close_notes = models.TextField(_("close-off notes"), blank=True)

    class Meta:
        ordering = ["status", "due_on", "-pk"]
        verbose_name = _("audit review")

    def __str__(self):
        return f"Audit {self.accounts_year}: {self.valuation}"

    def get_absolute_url(self):
        return reverse("valuations:valuation", args=[self.valuation_id]) + f"#audit-{self.pk}"

    @builtins.property
    def overdue(self):
        return bool(self.status == self.Status.OPEN and self.due_on and self.due_on < date.today())


class IndexPoint(models.Model):
    """A published index value, used to index asset values in the years between full valuations."""

    index = models.CharField(_("index"), max_length=100,
                             help_text=_("The same name as the asset class's index, for example BCIS All-in TPI."))
    on = models.DateField(_("date"))
    value = models.DecimalField(_("index value"), max_digits=12, decimal_places=3)
    source = models.CharField(_("source"), max_length=200, blank=True)

    class Meta:
        ordering = ["index", "-on"]
        constraints = [models.UniqueConstraint(fields=["index", "on"], name="index_point_unique")]
        verbose_name = _("index value")

    def __str__(self):
        return f"{self.index} {self.on:%d/%m/%Y}: {self.value}"

    @classmethod
    def at(cls, index, on):
        return cls.objects.filter(index__iexact=index, on__lte=on).first()
