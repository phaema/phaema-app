# SPDX-License-Identifier: AGPL-3.0-or-later
"""Content-Security-Policy and Permissions-Policy on every response.

The policy tells the browser to run only PHAEMA's own scripts, so a mistake that let someone's text into a page as
HTML could not run code. The two small inline scripts in the page layout carry a nonce, a random value made for each
request (``{{ request.csp_nonce }}``). Styles allow inline ``style`` attributes, which a few pages use for colours
and widths; a style cannot run code.

Map tiles come from OpenStreetMap and, when a key is set, Ordnance Survey. A council that adds another source can
list extra addresses in PHAEMA_CSP_IMG_SOURCES and PHAEMA_CSP_CONNECT_SOURCES.
"""
import secrets

from django.conf import settings

MAP_TILES = ("https://tile.openstreetmap.org", "https://*.tile.openstreetmap.org", "https://api.os.uk")


def _policy(nonce):
    img = ["'self'", "data:", "blob:", *MAP_TILES, *getattr(settings, "PHAEMA_CSP_IMG_SOURCES", [])]
    connect = ["'self'", *MAP_TILES, *getattr(settings, "PHAEMA_CSP_CONNECT_SOURCES", [])]
    parts = {
        "default-src": ["'self'"],
        "script-src": ["'self'", f"'nonce-{nonce}'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": img,
        "connect-src": connect,
        "font-src": ["'self'", "data:"],
        "worker-src": ["'self'", "blob:"],
        "frame-src": ["'self'"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'", *getattr(settings, "PHAEMA_CSP_FORM_ACTIONS", [])],
        "frame-ancestors": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in parts.items())


PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)
        # Static files carry no one's data; the e-learning page among them has its own inline script.
        static = request.path.startswith("/" + (settings.STATIC_URL or "static/").lstrip("/"))
        if getattr(settings, "PHAEMA_CSP_ENABLED", True) and not static and "Content-Security-Policy" not in response:
            header = "Content-Security-Policy-Report-Only" if getattr(settings, "PHAEMA_CSP_REPORT_ONLY", False) \
                else "Content-Security-Policy"
            response[header] = _policy(request.csp_nonce)
        response.setdefault("Permissions-Policy", PERMISSIONS)
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
