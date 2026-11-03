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
        help_text=_("Hold tenant rent accounts in PHAEMA. If off, demands are exported to the council's finance system."),
    )
    service_charges_enabled = models.BooleanField(_("service charge ledger"), default=False)
    maintenance_enabled = models.BooleanField(_("maintenance"), default=False)
    compliance_enabled = models.BooleanField(_("compliance"), default=True)
    golden_thread_enabled = models.BooleanField(_("Golden Thread"), default=True)

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
