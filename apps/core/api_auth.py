# SPDX-License-Identifier: AGPL-3.0-or-later
"""API sign-in with a username and password, for people without two-step sign-in only."""
from rest_framework import exceptions
from rest_framework.authentication import BasicAuthentication


class PasswordOnlyBasicAuthentication(BasicAuthentication):
    def authenticate_credentials(self, userid, password, request=None):
        from . import two_step

        user, auth = super().authenticate_credentials(userid, password, request)
        if two_step.has_two_step(user) or two_step.is_required(user):
            raise exceptions.AuthenticationFailed(
                "This account uses two-step sign-in, so it cannot use the API with a password alone. "
                "Sign in through the browser instead.")
        return user, auth
