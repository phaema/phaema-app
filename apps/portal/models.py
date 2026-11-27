# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tenant portal: people at a tenant who may sign in at /tenant/, their sign-in codes, and contact changes they ask
for. Portal accounts are not PHAEMA users: they never have a role and cannot open any staff page."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class PortalAccount(TimeStampedModel):
    party = models.ForeignKey("leases.Party", verbose_name=_("tenant"), on_delete=models.CASCADE,
                              related_name="portal_accounts")
    name = models.CharField(_("name"), max_length=200)
    email = models.EmailField(_("email"), unique=True,
                              help_text=_("Sign-in codes are sent here. Each person needs their own address."))
    finance = models.BooleanField(_("finance"), default=True,
                                  help_text=_("Can see the account, demands and payments, and ask to change contact "
                                              "details for demands."))
    facilities = models.BooleanField(_("facilities"), default=False,
                                     help_text=_("For repairs, certificates and service charges, as they are added "
                                                 "to the portal."))
    active = models.BooleanField(_("active"), default=True,
                                 help_text=_("Untick to stop this person signing in at once."))
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("invited by"), null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    invited_at = models.DateTimeField(_("invitation sent"), null=True, blank=True)
    last_sign_in = models.DateTimeField(_("last signed in"), null=True, blank=True)

    class Meta:
        ordering = ["party__name", "name"]
        verbose_name = _("tenant portal account")
        verbose_name_plural = _("tenant portal accounts")

    def __str__(self):
        return f"{self.name} ({self.party})"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


def _digest(account_id, code):
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"portal-code:{account_id}:{code}".encode(), hashlib.sha256).hexdigest()


class SignInCode(models.Model):
    """A one-time sign-in code, kept only as a keyed hash."""

    MINUTES = 15
    TRIES = 5

    account = models.ForeignKey(PortalAccount, on_delete=models.CASCADE, related_name="codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    tries = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, account):
        """Make a new code (cancelling any earlier ones) and return it with its plain text."""
        account.codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        code = f"{secrets.randbelow(1_000_000):06d}"
        row = cls.objects.create(account=account, code_hash=_digest(account.pk, code),
                                 expires_at=timezone.now() + timedelta(minutes=cls.MINUTES))
        return row, code

    def matches(self, code):
        """True if the code is right and still usable. Every try counts, right or wrong."""
        if self.used_at or self.expires_at < timezone.now() or self.tries >= self.TRIES:
            return False
        self.tries += 1
        ok = hmac.compare_digest(self.code_hash, _digest(self.account_id, code.strip()))
        if ok:
            self.used_at = timezone.now()
        self.save(update_fields=["tries", "used_at"])
        return ok


class ContactChange(models.Model):
    """New contact details for demands that a tenant asked for in the portal. Nothing changes until estates accept."""

    class Status(models.TextChoices):
        WAITING = "waiting", _("Waiting")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")

    lease = models.ForeignKey("leases.Lease", verbose_name=_("agreement"), on_delete=models.CASCADE,
                              related_name="contact_changes")
    account = models.ForeignKey(PortalAccount, verbose_name=_("asked by"), null=True, on_delete=models.SET_NULL,
                                related_name="contact_changes")
    contact_name = models.CharField(_("contact for demands"), max_length=200, blank=True)
    email = models.EmailField(_("email for demands"), blank=True)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    address = models.TextField(_("address for demands"), blank=True)
    note = models.TextField(_("note from the tenant"), blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.WAITING,
                              db_index=True)
    created_at = models.DateTimeField(_("asked"), auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("decided by"), null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(_("decided"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("contact change from a tenant")
        verbose_name_plural = _("contact changes from tenants")

    def __str__(self):
        return f"{self.lease.reference}: {self.get_status_display()}"

    FIELDS = {"contact_name": "billing_contact_name", "email": "billing_email", "phone": "billing_phone",
              "address": "billing_address"}

    def accept(self, user):
        lease = self.lease
        for mine, theirs in self.FIELDS.items():
            setattr(lease, theirs, getattr(self, mine))
        lease.save(update_fields=list(self.FIELDS.values()) + ["updated_at"])
        self.status, self.decided_by, self.decided_at = self.Status.ACCEPTED, user, timezone.now()
        self.save(update_fields=["status", "decided_by", "decided_at"])

    def decline(self, user):
        self.status, self.decided_by, self.decided_at = self.Status.DECLINED, user, timezone.now()
        self.save(update_fields=["status", "decided_by", "decided_at"])


class PortalMessage(models.Model):
    """A message between a tenant and the estates team about an agreement (and, if given, one of its requests).
    Answered by the property's managing surveyor, or whoever is covering for them."""

    class Direction(models.TextChoices):
        FROM_TENANT = "in", _("From the tenant")
        TO_TENANT = "out", _("To the tenant")

    lease = models.ForeignKey("leases.Lease", verbose_name=_("agreement"), on_delete=models.CASCADE,
                              related_name="portal_messages")
    case = models.ForeignKey("cases.Case", verbose_name=_("request"), null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="portal_messages")
    direction = models.CharField(_("direction"), max_length=3, choices=Direction.choices)
    account = models.ForeignKey(PortalAccount, verbose_name=_("tenant"), null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("from"), null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    text = models.TextField(_("message"))
    created_at = models.DateTimeField(_("sent"), auto_now_add=True)
    answered_at = models.DateTimeField(_("answered"), null=True, blank=True)
    read_at = models.DateTimeField(_("read by the tenant"), null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("tenant portal message")
        verbose_name_plural = _("tenant portal messages")

    def __str__(self):
        return f"{self.lease.reference}: {self.get_direction_display()} {self.created_at:%d %b %Y}"

    @property
    def sender(self):
        if self.direction == self.Direction.FROM_TENANT:
            return self.account.name if self.account else _("Tenant")
        return (self.author.get_full_name() or self.author.username) if self.author else _("Estates team")
