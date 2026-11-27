# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who is signed in to the tenant portal, and what they may see. Every portal view gets its agreements from
`agreements_for`, so a tenant can never reach another tenant's records."""
import time
from datetime import date, timedelta
from functools import wraps

from django.conf import settings
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect

from apps.core.middleware import set_api_user
from apps.core.models import ModuleSettings
from apps.leases.models import Lease

SESSION_KEY = "phaema_portal_account"
SEEN_KEY = "phaema_portal_seen"
VIA = "Tenant portal"
AFTER_END = timedelta(days=365)  # tenants keep access for 12 months after their agreement ends


def enabled():
    return ModuleSettings.load().tenant_portal_enabled


def agreements_for(account, today=None):
    """The agreements a portal account may see: let out by the council to the account's tenant, not just proposed,
    and not ended more than 12 months ago."""
    if account is None or not account.active:
        return Lease.objects.none()
    cutoff = (today or date.today()) - AFTER_END
    return (Lease.objects.filter(counterparty_id=account.party_id, direction=Lease.Direction.OUT)
            .exclude(status=Lease.Status.PROPOSED)
            .filter(Q(actual_end__isnull=True) | Q(actual_end__gte=cutoff))
            .filter(Q(term_end__isnull=True) | Q(term_end__gte=cutoff) | Q(status__in=[Lease.Status.CURRENT,
                                                                                         Lease.Status.HOLDING_OVER]))
            .order_by("reference"))


def may_sign_in(account):
    return account is not None and account.active and enabled() and agreements_for(account).exists()


def sign_in(request, account):
    request.session.cycle_key()
    request.session[SESSION_KEY] = account.pk
    request.session[SEEN_KEY] = int(time.time())


def sign_out(request):
    request.session.pop(SESSION_KEY, None)
    request.session.pop(SEEN_KEY, None)
    request.session.cycle_key()


def current(request):
    """The signed-in portal account, or None. Signs out after PHAEMA_PORTAL_IDLE_MINUTES without use."""
    from .models import PortalAccount

    pk = request.session.get(SESSION_KEY)
    if not pk:
        return None
    now = int(time.time())
    limit = settings.PHAEMA_PORTAL_IDLE_MINUTES * 60
    if limit and now - request.session.get(SEEN_KEY, 0) > limit:
        sign_out(request)
        return None
    account = PortalAccount.objects.select_related("party").filter(pk=pk).first()
    if not may_sign_in(account):
        sign_out(request)
        return None
    request.session[SEEN_KEY] = now
    return account


PORTAL_CSP = ("default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
              "img-src 'self' data:; connect-src 'self'; font-src 'self' data:; frame-src 'self'; object-src 'none'; "
              "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def portal_headers(response, request):
    """The portal's own, narrower content security policy (no map tiles), and no caching of tenants' pages."""
    if getattr(settings, "PHAEMA_CSP_ENABLED", True):
        response["Content-Security-Policy"] = PORTAL_CSP.format(nonce=getattr(request, "csp_nonce", ""))
    response["Cache-Control"] = "no-store"
    return response


def portal_page(view):
    """For pages that need no sign-in (sign-in itself): 404 when the portal is off, and the portal's headers."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not enabled():
            raise Http404
        request.portal_account = None
        return portal_headers(view(request, *args, **kwargs), request)
    return wrapped


def tenant_required(view):
    """For pages a signed-in tenant sees. Changes made on them are logged as made through the tenant portal."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not enabled():
            raise Http404
        account = current(request)
        if account is None:
            return portal_headers(redirect("portal:sign-in"), request)
        request.portal_account = account
        set_api_user(None, f"{VIA}: {account.name} <{account.email}>")
        return portal_headers(view(request, *args, **kwargs), request)
    return wrapped
