# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Base for PHAEMA records: creation and update times plus who made them."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


def days_list_validator(value):
    from django.core.exceptions import ValidationError

    parts = [p for p in value.replace(" ", "").split(",") if p]
    if not all(p.isdigit() and int(p) <= 1000 for p in parts):
        raise ValidationError(_("Enter whole numbers of days separated by commas, e.g. 180,90,30."))


class ModuleSettings(models.Model):
    """Single-row table holding which optional modules this council has switched on."""

    organisation_name = models.CharField(_("organisation name"), max_length=200, blank=True)
    rent_ledger_enabled = models.BooleanField(
        _("rent ledger"), default=False,
        help_text=_("Raise rent charges, keep tenant accounts and arrears, and export to the finance system."),
    )

    class Invoicing(models.TextChoices):
        PHAEMA = "phaema", _("PHAEMA numbers the invoices; finance records them")
        FINANCE = "finance", _("PHAEMA sends charges; the finance system raises the invoices")

    invoicing = models.CharField(_("who raises rent invoices"), max_length=10, choices=Invoicing.choices,
                                 default=Invoicing.PHAEMA)
    invoice_prefix = models.CharField(_("invoice number prefix"), max_length=10, default="PH",
                                      help_text=_("Put before invoice numbers, e.g. PH000123."))
    next_invoice_number = models.PositiveIntegerField(_("next invoice number"), default=1)
    vat_rate = models.DecimalField(_("standard VAT rate (%)"), max_digits=5, decimal_places=2, default=20,
                                   help_text=_("Added to rent on leases where the council has opted to tax."))
    rent_income_code = models.CharField(_("rent income code"), max_length=40, blank=True,
                                        help_text=_("Ledger code (cost centre and account) for rent income, "
                                                    "included in the finance export."))
    service_charge_income_code = models.CharField(
        _("service charge income code"), max_length=40, blank=True,
        help_text=_("Ledger code for service charge income, included in the finance export. "
                    "Leave blank to use the rent income code."))
    vat_code_standard = models.CharField(_("VAT code: standard rated"), max_length=10, default="S")
    vat_code_exempt = models.CharField(_("VAT code: exempt"), max_length=10, default="E")
    service_charges_enabled = models.BooleanField(_("service charge ledger"), default=False)
    maintenance_enabled = models.BooleanField(_("maintenance"), default=False)
    order_approval_limit = models.DecimalField(
        _("works orders needing approval (£, over)"), max_digits=10, decimal_places=2, default=5000,
        help_text=_("Works orders estimated above this need the job owner's supervisor to approve them."))
    compliance_enabled = models.BooleanField(_("compliance"), default=True)
    golden_thread_enabled = models.BooleanField(_("Golden Thread"), default=True)
    valuation_enabled = models.BooleanField(_("asset valuation"), default=False)
    open_data_enabled = models.BooleanField(
        _("publish open data"), default=False,
        help_text=_("Publish the Transparency Code land and assets list and the available property list at "
                    "/open-data/ under the Open Government Licence, without signing in."))

    class OsMapStyle(models.TextChoices):
        ROAD = "Road_3857", _("Road")
        OUTDOOR = "Outdoor_3857", _("Outdoor")
        LIGHT = "Light_3857", _("Light")

    os_maps_api_key = models.CharField(
        _("OS Maps API key"), max_length=100, blank=True,
        help_text=_("Your council's Ordnance Survey Data Hub key (free under the Public Sector Geospatial "
                    "Agreement). Leave blank to use OpenStreetMap only. The key is sent to users' browsers, "
                    "so restrict it to your PHAEMA web address in the OS Data Hub."),
    )
    os_map_style = models.CharField(_("OS map style"), max_length=20, choices=OsMapStyle.choices,
                                    default=OsMapStyle.ROAD)

    brand_colour = models.CharField(
        _("header colour"), max_length=7, blank=True,
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", _("Enter a colour like #1d3557."))],
        help_text=_("Your council's colour for the PHAEMA header, as a hex code such as #1d3557. "
                    "Choose a dark colour so the white header text stays readable. Leave blank for the default."),
    )

    reminder_days_review = models.CharField(
        _("rent review reminders (days before)"), max_length=60, default="180,90,30",
        validators=[days_list_validator])
    reminder_days_notice = models.CharField(
        _("break notice reminders (days before)"), max_length=60, default="180,90,30,7",
        validators=[days_list_validator])
    reminder_days_break = models.CharField(
        _("break date reminders (days before)"), max_length=60, default="30",
        validators=[days_list_validator])
    reminder_days_expiry = models.CharField(
        _("lease expiry reminders (days before)"), max_length=60, default="365,180,90",
        validators=[days_list_validator])
    reminder_days_other = models.CharField(
        _("other event reminders (days before)"), max_length=60, default="30,7",
        validators=[days_list_validator])
    overdue_reminders = models.BooleanField(
        _("weekly overdue reminders"), default=True,
        help_text=_("Every Monday, remind people of their overdue events."))

    def reminder_days(self, event_type):
        raw = getattr(self, f"reminder_days_{event_type}", "") or ""
        return sorted({int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}, reverse=True)

    class Meta:
        verbose_name = _("module settings")
        verbose_name_plural = _("module settings")

    def __str__(self):
        return "Module settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # The settings row cannot be deleted.

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class AuditEntry(models.Model):
    """Immutable record of every create, change and delete on audited records."""

    class Action(models.TextChoices):
        CREATE = "create", _("Created")
        UPDATE = "update", _("Changed")
        DELETE = "delete", _("Deleted")

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64, db_index=True)
    object_repr = models.CharField(max_length=255)
    action = models.CharField(max_length=10, choices=Action.choices)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = _("audit entry")
        verbose_name_plural = _("audit entries")

    def __str__(self):
        return f"{self.get_action_display()} {self.object_repr} at {self.timestamp:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Audit entries cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit entries cannot be deleted.")


class StaffProfile(models.Model):
    """Extra details for a PHAEMA user: who supervises them and approves their work."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    job_title = models.CharField(_("job title"), max_length=100, blank=True)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="supervisees",
        verbose_name=_("supervisor and approver"),
        help_text=_("Approves this person's work at the approval points in cases, such as decisions on consents."))

    class Meta:
        verbose_name = _("supervisor and job title")
        verbose_name_plural = _("supervisor and job title")

    def __str__(self):
        return f"{self.user}"


def supervisor_of(user):
    profile = StaffProfile.objects.filter(user=user).select_related("supervisor").first()
    return profile.supervisor if profile and profile.supervisor and profile.supervisor.is_active else None
