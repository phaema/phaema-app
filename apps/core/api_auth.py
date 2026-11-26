# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing in to the API.

API tokens (ApiTokenAuthentication) are the normal way: ``Authorization: Bearer phaema_...``. Each token is limited
to read only or read and change, to parts of the API, and to an end date, and can be cancelled on its own.

A username and password (HTTP Basic) is refused unless PHAEMA_API_PASSWORD_SIGN_IN is on, and even then only for
accounts without two-step sign-in. It is kept for councils with scripts written before tokens existed.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, BasicAuthentication, get_authorization_header

from .middleware import set_api_user


class ApiTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].decode(errors="ignore").lower() not in ("bearer", "token"):
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Send the token as: Authorization: Bearer <token>.")
        try:
            key = parts[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("That token is not valid.") from None
        return self.authenticate_key(key, request)

    def authenticate_key(self, key, request):
        from .models import ApiToken
        from .outside import access_ended
        from .roles import has_role
        from .throttle import client_ip

        token = ApiToken.objects.select_related("user").filter(key_hash=ApiToken.hash(key)).first()
        if token is None:
            raise exceptions.AuthenticationFailed("That token is not valid.")
        if token.revoked_at is not None:
            raise exceptions.AuthenticationFailed("That token has been cancelled.")
        if not token.is_live():
            raise exceptions.AuthenticationFailed("That token has passed its end date.")
        user = token.user
        if not user.is_active or access_ended(user) or not has_role(user):
            raise exceptions.AuthenticationFailed("The account this token acts for can no longer use PHAEMA.")
        now = timezone.now()
        if token.last_used_at is None or now - token.last_used_at > timedelta(minutes=1):
            ip = client_ip(getattr(request, "_request", request))[:45]
            ApiToken.objects.filter(pk=token.pk).update(last_used_at=now, last_used_from=ip)  # not a change to log
        set_api_user(user, f"API token: {token}")
        return user, token

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


class PasswordOnlyBasicAuthentication(BasicAuthentication):
    def authenticate(self, request):
        if not getattr(settings, "PHAEMA_API_PASSWORD_SIGN_IN", False):
            return None
        return super().authenticate(request)

    def authenticate_credentials(self, userid, password, request=None):
        from . import two_step

        user, auth = super().authenticate_credentials(userid, password, request)
        if two_step.has_two_step(user) or two_step.is_required(user):
            raise exceptions.AuthenticationFailed(
                "This account uses two-step sign-in, so it cannot use the API with a password alone. "
                "Ask an administrator for an API token.")
        set_api_user(user, "API: username and password")
        return user, auth


try:  # describe the token in the API documentation (/api/docs/)
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class ApiTokenScheme(OpenApiAuthenticationExtension):
        target_class = "apps.core.api_auth.ApiTokenAuthentication"
        name = "apiToken"

        def get_security_definition(self, auto_schema):
            return {"type": "http", "scheme": "bearer",
                    "description": "An API token made by an administrator in Manage data, API tokens."}

    class PasswordScheme(OpenApiAuthenticationExtension):
        target_class = "apps.core.api_auth.PasswordOnlyBasicAuthentication"
        name = "password"

        def get_security_definition(self, auto_schema):
            return {"type": "http", "scheme": "basic",
                    "description": "Username and password. Refused unless the server sets "
                                   "PHAEMA_API_PASSWORD_SIGN_IN, and never for accounts with two-step sign-in."}
except ImportError:  # pragma: no cover
    pass
