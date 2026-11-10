# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connectors: optional links to other systems. All are off until an administrator turns them on."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import AccessArea
from apps.core.roles import ROLES


class SsoIdentity(models.Model):
    """Links a PHAEMA user to their account in the council's sign-in service (Microsoft Entra ID and others).

    Made the first time the person signs in that way. Deleting it unlinks them: they are matched again by email
    address the next time."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sso_identity")
    issuer = models.CharField(_("sign-in service"), max_length=255)
    subject = models.CharField(_("their ID in the sign-in service"), max_length=255)
    email = models.CharField(_("email address at last sign-in"), max_length=254, blank=True)
    linked_at = models.DateTimeField(_("linked"), auto_now_add=True)
    last_sign_in = models.DateTimeField(_("last signed in this way"), null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["issuer", "subject"], name="sso_identity_unique")]
        verbose_name = _("council sign-in link")
        verbose_name_plural = _("council sign-in link")

    def __str__(self):
        return f"Council sign-in for {self.user}"


class SsoGroupMapping(models.Model):
    """Gives everyone in a group of the council's sign-in service a PHAEMA role, an access area, or both."""

    group = models.CharField(
        _("group"), max_length=255,
        help_text=_("Exactly as the sign-in service sends it. For Microsoft Entra ID this is the group's Object ID "
                    "(for example 0a1b2c3d-1111-2222-3333-444455556666) or the value of an app role."))
    label = models.CharField(_("what the group is"), max_length=120, blank=True,
                             help_text=_("For your own reference, for example: Estates surveyors."))
    role = models.CharField(_("role"), max_length=30, blank=True, choices=[(r, r) for r in ROLES])
    access_area = models.ForeignKey(AccessArea, on_delete=models.CASCADE, null=True, blank=True,
                                    verbose_name=_("access area"))

    class Meta:
        ordering = ["label", "group"]
        verbose_name = _("sign-in group mapping")
        verbose_name_plural = _("sign-in group mappings")

    def __str__(self):
        gives = " and ".join(str(x) for x in (self.role, self.access_area) if x)
        return f"{self.label or self.group}: {gives or 'nothing'}"
