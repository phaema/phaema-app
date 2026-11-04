# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Hand over work page: move a person's properties, cases and tasks to others in one step."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import handover, places
from .roles import CONTRIBUTORS, administrators_only

User = get_user_model()


def _name(user):
    return user.get_full_name() or user.username


def _int(value):
    return int(value) if str(value or "").isdigit() else None


@administrators_only
def hand_over(request):
    source = request.POST if request.method == "POST" else request.GET
    old_id = _int(source.get("from"))
    old = get_object_or_404(User, pk=old_id) if old_id else None
    building = _int(source.get("building"))
    building_obj = places.buildings().filter(pk=building).first() if building else None
    if building and building_obj is None:
        building = None

    if old and request.method == "POST":
        choices, wrong = {}, []
        rows = handover.summary(old, building)
        for item, count, receivers in rows:
            pick = _int(request.POST.get(f"to_{item.key}"))
            if pick:
                match = next((u for u in receivers if u.pk == pick), None)
                if match is None:
                    wrong.append(item.label)
                else:
                    choices[item.key] = match
        if wrong:
            messages.error(request, _("Choose someone who can receive: %(items)s.") % {"items": ", ".join(map(str, wrong))})
        else:
            moved = handover.hand_over(old, choices, building)
            stopped = False
            if request.POST.get("deactivate") and old != request.user and old.is_active and (
                    request.user.is_superuser or not old.is_superuser):
                old.is_active = False
                old.save(update_fields=["is_active"])
                stopped = True
            labels = {item.key: item.label for item in handover.items()}
            done = [f"{labels[k]}: {n} to {_name(choices[k])}" for k, n in moved.items()]
            if done:
                messages.success(request, _("Handed over from %(name)s. %(list)s.") % {
                    "name": _name(old), "list": "; ".join(done)})
            else:
                messages.info(request, _("Nothing was moved."))
            if stopped:
                messages.success(request, _("%(name)s can no longer sign in.") % {"name": _name(old)})
            url = reverse("hand-over") + f"?from={old.pk}"
            return redirect(url + (f"&building={building}" if building else ""))

    context = {"people": User.objects.order_by("-is_active", "first_name", "last_name", "username"),
               "old": old, "buildings": places.buildings(), "building": building_obj}
    if old:
        default = _int(request.GET.get("to"))
        rows = []
        for item, count, receivers in handover.summary(old, building):
            chosen = default if any(u.pk == default for u in receivers) else None
            rows.append({"item": item, "count": count, "receivers": receivers, "chosen": chosen,
                         "limited_out": bool(building and not item.paths)})
        context.update({
            "rows": rows, "total": sum(r["count"] for r in rows), "default": default,
            "everyone": handover.candidates(handover.STAFF + (CONTRIBUTORS,), exclude=old),
            "can_deactivate": old.is_active and old != request.user and (request.user.is_superuser
                                                                          or not old.is_superuser),
            "valuer": getattr(old, "valuer", None),
        })
    return render(request, "core/hand_over.html", context)
