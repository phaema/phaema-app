# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cover for absence: one person sees another's patch (rent, arrears, service charges) until a set date.

Administrators can arrange cover for anyone. Supervisors can arrange cover for anyone in their supervision chain."""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from . import access
from .models import Cover
from .roles import ADMINISTRATORS, SURVEYORS, is_administrator

User = get_user_model()


def _staff():
    return (User.objects.filter(is_active=True).filter(Q(groups__name__in=(ADMINISTRATORS, SURVEYORS))
                                                       | Q(is_superuser=True))
            .distinct().order_by("first_name", "last_name", "username"))


def coverable(user):
    """People this user may arrange cover for."""
    if is_administrator(user):
        return list(_staff())
    return list(_staff().filter(pk__in=access.chain(user)))


def can_arrange(user):
    return getattr(user, "is_authenticated", False) and bool(coverable(user))


def _name(u):
    return u.get_full_name() or u.username


def _date(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


@login_required
def cover(request):
    if not can_arrange(request.user):
        raise PermissionDenied
    allowed = coverable(request.user)
    allowed_ids = {u.pk for u in allowed}
    today = date.today()
    errors, form = [], {"covered": "", "user": "", "starts_on": today.isoformat(), "ends_on": "", "reason": ""}

    if request.method == "POST" and "end" in request.POST:
        item = get_object_or_404(Cover, pk=request.POST.get("end"))
        if item.covered_id not in allowed_ids:
            raise PermissionDenied
        if item.starts_on >= today:
            item.delete()
            messages.success(request, _("Cover cancelled."))
        else:
            item.ends_on = today - timedelta(days=1)
            item.save()
            messages.success(request, _("Cover ended."))
        return redirect("cover")

    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip() for k in form}
        covered = next((u for u in allowed if str(u.pk) == form["covered"]), None)
        person = _staff().filter(pk=form["user"]).first() if form["user"].isdigit() else None
        starts, ends = _date(form["starts_on"]), _date(form["ends_on"])
        if covered is None:
            errors.append(("covered", _("Choose who is away.")))
        if person is None:
            errors.append(("user", _("Choose who is covering.")))
        elif covered is not None and person.pk == covered.pk:
            errors.append(("user", _("Someone cannot cover for themselves.")))
        if starts is None:
            errors.append(("starts_on", _("Enter the date cover starts, for example 2026-11-20.")))
        if ends is None:
            errors.append(("ends_on", _("Enter the date cover ends, for example 2026-11-27.")))
        elif starts and ends < starts:
            errors.append(("ends_on", _("Cover must end on or after the day it starts.")))
        elif ends and ends > today + timedelta(days=366):
            errors.append(("ends_on", _("Cover can be arranged for up to a year at a time.")))
        if not errors:
            Cover.objects.create(user=person, covered=covered, starts_on=starts, ends_on=ends,
                                 reason=form["reason"][:200], created_by=request.user)
            messages.success(request, _("%(who)s is covering for %(whom)s until %(until)s.") % {
                "who": _name(person), "whom": _name(covered), "until": ends.strftime("%-d %B %Y")})
            return redirect("cover")

    current = (Cover.objects.filter(ends_on__gte=today, covered__in=allowed_ids)
               .select_related("user", "covered", "created_by").order_by("starts_on", "pk"))
    return render(request, "core/cover.html", {
        "current": current, "allowed": allowed, "staff": _staff(), "form": form, "errors": errors,
        "error_fields": {k: v for k, v in errors}, "today": today,
    })
