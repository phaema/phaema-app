# SPDX-License-Identifier: AGPL-3.0-or-later
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Report(TimeStampedModel):
    """A saved report: which records, which columns, which filters and in what order."""

    name = models.CharField(_("name"), max_length=120)
    description = models.CharField(_("description"), max_length=255, blank=True)
    dataset = models.CharField(_("records"), max_length=30)
    columns = models.JSONField(_("columns"), default=list)
    filters = models.JSONField(_("filters"), default=dict, blank=True)
    sort_by = models.CharField(_("sort by"), max_length=60, blank=True)
    sort_descending = models.BooleanField(_("largest or latest first"), default=False)
    show_totals = models.BooleanField(_("show totals"), default=True,
                                      help_text=_("Add a total line for money and area columns."))
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="reports")
    shared = models.BooleanField(_("share with everyone"), default=False)
    starter = models.CharField(max_length=40, blank=True, editable=False,
                               help_text=_("Set for the reports PHAEMA provides."))

    class Meta:
        ordering = ["name"]
        verbose_name = _("report")
        verbose_name_plural = _("reports")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("reports:run", args=[self.pk])

    def can_change(self, user):
        from apps.core.roles import is_administrator

        if self.starter:
            return is_administrator(user)
        return self.owner_id == user.pk or is_administrator(user)

    def visible_to(self, user):
        """Shared and ready-made reports are open to all; private ones to their owner and administrators."""
        from apps.core.roles import is_administrator

        return bool(self.shared or self.starter or self.owner_id == user.pk or is_administrator(user))
