# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signing in with either a username or an email address."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Django's usual sign-in, plus the email address in place of the username.

    The username is tried first. Email addresses are not unique in Django, so an address only works when
    exactly one sign-in has it: if two people share an address, both must use their usernames.
    """

    def user_can_authenticate(self, user):
        from .outside import access_ended

        return super().user_can_authenticate(user) and not access_ended(user)

    def get_user(self, user_id):
        # A session whose access has ended still finds its user, so the access-ended middleware can sign the
        # person out and say why, rather than sending them to the sign-in page without explanation.
        User = get_user_model()
        try:
            user = User._default_manager.get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if super().user_can_authenticate(user) else None

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        from . import throttle

        if throttle.blocked(username, request):
            if request is not None:
                request.phaema_signin_blocked = True
            return None
        user = self._check(username, password)
        if user is None:
            throttle.record_failure(username, request)
        else:
            throttle.clear(username)
        return user

    def _check(self, username, password):
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
