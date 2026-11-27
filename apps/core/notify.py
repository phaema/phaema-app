# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sending emails to tenants through GOV.UK Notify.

Every email is first saved as an OutgoingEmail, so the estates team can see what each tenant was sent. If IT has set
PHAEMA_NOTIFY_API_KEY and PHAEMA_NOTIFY_TEMPLATE_ID, it is then passed to Notify; otherwise it stays "recorded, not
sent". The template is one the council creates in Notify with the subject ((subject)) and the body ((body)), so
PHAEMA keeps the wording. Notify's "test" keys work too: Notify accepts the email but does not deliver it.
"""
from django.conf import settings
from django.utils import timezone

from .models import OutgoingEmail


def configured():
    return bool(settings.PHAEMA_NOTIFY_API_KEY and settings.PHAEMA_NOTIFY_TEMPLATE_ID)


def _client():
    from notifications_python_client.notifications import NotificationsAPIClient

    return NotificationsAPIClient(settings.PHAEMA_NOTIFY_API_KEY)


def send(email: OutgoingEmail, body=None):
    """Pass a saved email to Notify, if a key is set, and record what happened. `body` sends different text from the
    one recorded, for emails such as sign-in codes whose secret part must not be kept."""
    if not configured():
        email.status = OutgoingEmail.Status.RECORDED
        email.save(update_fields=["status"])
        return email
    try:
        response = _client().send_email_notification(
            email_address=email.to, template_id=settings.PHAEMA_NOTIFY_TEMPLATE_ID,
            personalisation={"subject": email.subject, "body": body if body is not None else email.body}, reference=f"phaema-{email.pk}")
    except Exception as exc:  # the client raises HTTPError and others; any failure is recorded, not raised
        email.status, email.error = OutgoingEmail.Status.FAILED, str(exc)[:2000]
        email.save(update_fields=["status", "error"])
        return email
    email.status, email.notify_id, email.sent_at = OutgoingEmail.Status.SENT, str(response.get("id", "")), timezone.now()
    email.save(update_fields=["status", "notify_id", "sent_at"])
    return email
