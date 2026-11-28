# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class MigrationRun(models.Model):
    """One trial or real import of a file, kept so a council can show what was moved into PHAEMA, how it was
    checked against the old system, and who accepted it."""

    class Mode(models.TextChoices):
        TRIAL = "trial", _("Trial run (nothing saved)")
        LIVE = "live", _("Imported")

    kind = models.CharField(_("what was imported"), max_length=40)
    title = models.CharField(_("import"), max_length=100)
    mode = models.CharField(_("run"), max_length=8, choices=Mode.choices)
    filename = models.CharField(_("file"), max_length=255)
    file_sha256 = models.CharField(_("file fingerprint (SHA-256)"), max_length=64)
    run_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
                               verbose_name=_("run by"))
    run_at = models.DateTimeField(_("run at"), auto_now_add=True)
    rows = models.PositiveIntegerField(_("rows"), default=0)
    summary = models.JSONField(_("counts"), default=list, blank=True)  # [[label, new, updated, unchanged]]
    controls = models.JSONField(_("control totals"), default=list, blank=True)
    warnings = models.PositiveIntegerField(_("rows with warnings"), default=0)
    report = models.FileField(_("report"), upload_to="imports/reports/", blank=True)
    signed_off_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="+", verbose_name=_("signed off by"))
    signed_off_at = models.DateTimeField(_("signed off at"), null=True, blank=True)
    sign_off_note = models.TextField(_("sign-off note"), blank=True)

    class Meta:
        ordering = ["-run_at"]
        verbose_name = _("migration run")
        verbose_name_plural = _("migration runs")

    def __str__(self):
        return f"{self.title}: {self.get_mode_display()}, {self.filename}"

    def get_absolute_url(self):
        return reverse("imports:run", args=[self.pk])

    @property
    def reconciled(self):
        """True when every control total with an old-system figure matches both the file and PHAEMA."""
        checked = [c for c in self.controls if c.get("expected") not in (None, "")]
        return bool(checked) and all(c.get("matches") for c in checked)

    @property
    def mismatches(self):
        return [c for c in self.controls if c.get("matches") is False]


class ImportMapping(models.Model):
    """How another system's export headings match PHAEMA's columns, saved so the next export from the same system
    imports without matching them again."""

    kind = models.CharField(_("import"), max_length=40)
    sheet = models.CharField(_("sheet"), max_length=60)
    name = models.CharField(_("name"), max_length=80, help_text=_("For example \"Old system: lease export\"."))
    mapping = models.JSONField(_("columns"), default=dict)  # {the file's heading, lower case: PHAEMA field}
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "name"]
        unique_together = [("kind", "name")]
        verbose_name = _("saved column matching")
        verbose_name_plural = _("saved column matchings")

    def __str__(self):
        return self.name

    def fits(self, headings):
        """True if every heading this matching names is in the file."""
        have = {h.strip().lower() for h in headings}
        return bool(self.mapping) and set(self.mapping) <= have
