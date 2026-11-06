# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two-step sign-in (multi-factor authentication) with an authenticator app.

Codes are time-based one-time passwords (TOTP, RFC 6238: SHA-1, six digits, 30-second steps), which every common
authenticator app supports (Microsoft Authenticator, Google Authenticator, Authy, FreeOTP, Aegis and others).
A code is accepted for one step either side of now, to allow for clock drift, and only once.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10


def new_secret():
    """A random 160-bit secret, in base32 as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def code_at(secret, step):
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def current_step(now=None):
    return int((now if now is not None else time.time()) // STEP_SECONDS)


def clean_code(code):
    return "".join(ch for ch in (code or "") if ch.isalnum())


def matching_step(secret, code, after_step=0, now=None):
    """The time step the code belongs to, or None. Steps at or before after_step are refused (no reuse)."""
    code = clean_code(code)
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if candidate > after_step and hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def setup_uri(secret, username):
    """The otpauth:// link an authenticator app reads from the QR code."""
    issuer = getattr(settings, "PHAEMA_ORGANISATION_NAME", "") or "PHAEMA"
    label = quote(f"PHAEMA ({issuer}):{username}")
    return f"otpauth://totp/{label}?" + urlencode(
        {"secret": secret, "issuer": f"PHAEMA ({issuer})", "algorithm": "SHA1", "digits": DIGITS,
         "period": STEP_SECONDS})


def qr_svg(text):
    """The QR code as inline SVG (no images to store, nothing sent to another site)."""
    import segno

    return segno.make(text, error="m").svg_inline(scale=5, dark="#0b0c0c", light="#ffffff")


def spaced(secret):
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


# Who has and who needs two-step sign-in

def has_two_step(user):
    from .models import TwoStepDevice

    return bool(user is not None and user.pk and TwoStepDevice.objects.filter(user=user).exists())


def is_required(user):
    """Whether this person must use two-step sign-in, under the council's setting."""
    from .models import ModuleSettings
    from .roles import is_administrator

    if (getattr(settings, "PHAEMA_DEMO_SITE", False) or not getattr(settings, "PHAEMA_ENFORCE_TWO_STEP", True)
            or not user or not user.pk):
        return False
    rule = ModuleSettings.load().two_step_required
    if rule == ModuleSettings.TwoStep.EVERYONE:
        return True
    if rule == ModuleSettings.TwoStep.ADMINISTRATORS:
        return bool(user.is_superuser or is_administrator(user))
    return False


# Checking codes

def verify(user, code):
    """Check an authenticator code or an unused recovery code. Returns "app", "recovery" or None."""
    from .models import RecoveryCode, TwoStepDevice

    with transaction.atomic():
        device = TwoStepDevice.objects.select_for_update().filter(user=user).first()
        if device is None:
            return None
        step = matching_step(device.secret, code, after_step=device.last_step)
        if step is not None:
            device.last_step = step
            device.save(update_fields=["last_step"])
            return "app"
        recovery = clean_code(code).lower()
        if len(recovery) == 10:
            for saved in RecoveryCode.objects.select_for_update().filter(user=user, used_at__isnull=True):
                if check_password(recovery, saved.code_hash):
                    saved.used_at = timezone.now()
                    saved.save(update_fields=["used_at"])
                    return "recovery"
    return None


def new_recovery_codes(user):
    """Replace the person's recovery codes. Returns the codes to show once, formatted xxxxx-xxxxx."""
    from .models import RecoveryCode

    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o or 1/l/i, which are easily confused
    codes = ["".join(secrets.choice(alphabet) for _ in range(10)) for _ in range(RECOVERY_CODE_COUNT)]
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create(
            [RecoveryCode(user=user, code_hash=make_password(code)) for code in codes])
    return [f"{code[:5]}-{code[5:]}" for code in codes]


def recovery_codes_left(user):
    from .models import RecoveryCode

    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def turn_on(user, secret, code):
    """Confirm set-up with a first code from the app. Returns the recovery codes, or None if the code is wrong."""
    from . import audit
    from .models import TwoStepDevice

    step = matching_step(secret, code)
    if step is None:
        return None
    TwoStepDevice.objects.update_or_create(user=user, defaults={"secret": secret, "last_step": step})
    audit._record(user, "update", {"two-step sign-in": [None, "turned on"]})
    return new_recovery_codes(user)


def turn_off(user, by=None):
    """Remove the person's authenticator app and recovery codes (they set it up again to use it)."""
    from . import audit
    from .models import RecoveryCode, TwoStepDevice

    TwoStepDevice.objects.filter(user=user).delete()
    RecoveryCode.objects.filter(user=user).delete()
    how = "turned off" if by is None or by == user else f"reset by {by.get_full_name() or by.username}"
    audit._record(user, "update", {"two-step sign-in": [None, how]})
