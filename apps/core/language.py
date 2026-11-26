# SPDX-License-Identifier: AGPL-3.0-or-later
"""English or Welsh, chosen by each person.

Django's own LocaleMiddleware would follow the browser's language, which could show Welsh where the council has not
switched it on (the Welsh text is a draft until a translator has checked it). PHAEMA instead uses English unless the
council offers Welsh (Module settings) and the person has chosen Cymraeg at the top of the page, which sets a cookie.
"""
from django.conf import settings
from django.db import DatabaseError
from django.utils import translation
from django.utils.cache import patch_vary_headers

DEFAULT = "en"


def welsh_offered():
    from .models import ModuleSettings

    try:
        return bool(ModuleSettings.load().welsh_enabled)
    except DatabaseError:  # before the first migration
        return False


def language_for(request):
    chosen = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    if chosen == "cy" and welsh_offered():
        return "cy"
    return DEFAULT


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = language_for(request)
        translation.activate(language)
        request.LANGUAGE_CODE = language
        response = self.get_response(request)
        patch_vary_headers(response, ["Cookie"])
        response.headers.setdefault("Content-Language", language)
        translation.deactivate()
        return response
