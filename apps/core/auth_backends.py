# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing in with either a username or an email address."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Django's usual sign-in, plus the email address in place of the username.

    The username is tried first. Email addresses are not unique in Django, so an address only works when
    exactly one sign-in has it: if two people share an address, both must use their usernames.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        User = get_user_model()
        user = User._default_manager.filter(username=username).first()
        if user is None and "@" in username:
            matches = list(User._default_manager.filter(email__iexact=username.strip())[:2])
            user = matches[0] if len(matches) == 1 else None
        if user is None:
            User().set_password(password)  # do the same work as a real check, so timing gives nothing away
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            from apps.connectors import sso

            # Where the council requires its own sign-in, a correct password is refused like a wrong one.
            return user if sso.password_allowed(user) else None
        return None
