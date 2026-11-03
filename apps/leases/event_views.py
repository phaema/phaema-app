# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lease events: the list, each event's page with its action, the calendar feed and rent schedule changes."""
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.core.roles import can_edit, has_role
from apps.core.tables import sortable
from apps.reports.mixins import ExportMixin

from . import forms as f
from . import workflow
from .models import CalendarFeed, Lease, LeaseEvent, RentScheduleEntry

COLUMNS = {
    "due": (_("Due"), ["due_date", "pk"], False),
    "event": (_("Event"), ["event_type", "due_date"], False),
    "lease": (_("Agreement"), ["lease__reference", "due_date"], False),
    "assigned": (_("Assigned to"), ["assigned_to__first_name", "assigned_to__username", "due_date"], False),
    "status": (_("Status"), ["status", "due_date"], False),
}
WINDOWS = [("overdue", _("Overdue")), ("30", _("Due within 30 days")), ("90", _("Due within 3 months")),
           ("183", _("Due within 6 months")), ("365", _("Due within 12 months"))]
STATUS_FILTERS = [("open", _("To do or in progress")), ("done", _("Completed")), ("lapsed", _("Lapsed")),
                  ("all", _("All"))]


class EventListView(LoginRequiredMixin, ExportMixin, ListView):
    model = LeaseEvent
    export_dataset, export_title = "events", "Lease events"
    paginate_by = 50
    template_name = "leases/event_list.html"

    def get_queryset(self):
        get = self.request.GET
        qs = LeaseEvent.objects.select_related("lease", "lease__counterparty", "assigned_to")
        status = get.get("status", "open")
        if status == "open":
            qs = qs.filter(status__in=workflow.OPEN)
        elif status in ("done", "lapsed"):
            qs = qs.filter(status=status)
        if get.get("type"):
            qs = qs.filter(event_type=get["type"])
        who = get.get("assigned", "")
        if who == "me":
            qs = qs.filter(assigned_to=self.request.user)
        elif who == "none":
            qs = qs.filter(assigned_to__isnull=True)
        elif who.isdigit():
            qs = qs.filter(assigned_to_id=int(who))
        window, today = get.get("window", ""), date.today()
        if window == "overdue":
            qs = qs.filter(due_date__lt=today, status__in=workflow.OPEN)
        elif window.isdigit():
            qs = qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=int(window)))
        q = get.get("q", "").strip()
        if q:
            qs = qs.filter(Q(lease__reference__icontains=q) | Q(lease__counterparty__name__icontains=q)
                           | Q(title__icontains=q) | Q(lease__properties__name__icontains=q)).distinct()
        ordering, self.headings = sortable(self.request, COLUMNS, "due")
        return qs.order_by(*ordering)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        officers = f.officer_choices()
        ctx.update({
            "q": get.get("q", ""),
            "filters": [
                ("status", _("Status"), STATUS_FILTERS, get.get("status", "open"), False),
                ("type", _("Event"), LeaseEvent.EventType.choices, get.get("type", ""), True),
                ("window", _("When"), WINDOWS, get.get("window", ""), True),
                ("assigned", _("Assigned to"), [("me", _("Me")), ("none", _("Nobody"))]
                 + [(str(u.pk), u.get_full_name() or u.username) for u in officers], get.get("assigned", ""), True),
            ],
            "headings": self.headings,
            "today": date.today(),
        })
        params = get.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


def _outcome_form(event, data=None):
    initial = {}
    if event.event_type == LeaseEvent.EventType.REVIEW:
        nxt = workflow.suggested_next_review(event)
        initial = {"new_rent": event.lease.annual_rent, "effective_from": event.due_date, "next_review_date": nxt}
        return f.ReviewOutcomeForm(data, initial=initial)
    if event.event_type in (LeaseEvent.EventType.BREAK, LeaseEvent.EventType.BREAK_NOTICE):
        return f.BreakOutcomeForm(data, event=event)
    if event.event_type == LeaseEvent.EventType.EXPIRY:
        return f.ExpiryOutcomeForm(data)
    return f.OtherOutcomeForm(data)


@login_required
def event_detail(request, pk):
    event = get_object_or_404(LeaseEvent.objects.select_related("lease", "lease__counterparty", "assigned_to",
                                                                "completed_by"), pk=pk)
    editable = can_edit(request.user, event)
    outcome_form = _outcome_form(event) if editable and event.is_open else None
    edit_form = f.EventEditForm(instance=event) if editable and event.is_open else None

    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        if "save_details" in request.POST:
            edit_form = f.EventEditForm(request.POST, instance=event)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, _("Event updated."))
                return redirect(event)
        elif "record_outcome" in request.POST and event.is_open:
            outcome_form = _outcome_form(event, request.POST)
            if outcome_form.is_valid():
                d = outcome_form.cleaned_data
                if event.event_type == LeaseEvent.EventType.REVIEW:
                    workflow.complete_review(event, request.user, d["new_rent"], d["effective_from"],
                                             d["next_review_date"], d["notes"])
                elif event.event_type in (LeaseEvent.EventType.BREAK, LeaseEvent.EventType.BREAK_NOTICE):
                    workflow.complete_break(event, request.user, d["outcome"], d["notes"])
                elif event.event_type == LeaseEvent.EventType.EXPIRY:
                    workflow.complete_expiry(event, request.user, d["outcome"], d["end_date"], d["notes"])
                else:
                    workflow.complete_other(event, request.user, d["status"], d["notes"])
                messages.success(request, _("Outcome recorded."))
                return redirect(event.lease)
    return render(request, "leases/event_detail.html", {
        "event": event, "editable": editable, "outcome_form": outcome_form, "edit_form": edit_form,
        "rag": event.rag(),
    })


@login_required
def event_add(request, lease_pk):
    lease = get_object_or_404(Lease, pk=lease_pk)
    if not can_edit(request.user, lease):
        raise PermissionDenied
    form = f.NewEventForm(request.POST or None, initial={"assigned_to": workflow.default_assignee(lease)})
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.lease, event.event_type = lease, LeaseEvent.EventType.OTHER
        event.save()
        messages.success(request, _("Event added."))
        return redirect(lease)
    return render(request, "leases/event_add.html", {"lease": lease, "form": form})


# ---------------------------------------------------------------- rent schedule

@login_required
def rent_step_add(request, lease_pk):
    lease = get_object_or_404(Lease, pk=lease_pk)
    if not can_edit(request.user, lease):
        raise PermissionDenied
    form = f.RentStepForm(request.POST or None, lease=lease, initial={"reason": RentScheduleEntry.Reason.STEP})
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.lease = lease
        entry.save()
        messages.success(request, _("Rent schedule updated."))
        return redirect(lease)
    return render(request, "leases/rent_step_add.html", {"lease": lease, "form": form})


@login_required
@require_POST
def rent_step_delete(request, pk):
    entry = get_object_or_404(RentScheduleEntry, pk=pk)
    if not can_edit(request.user, entry):
        raise PermissionDenied
    if entry.lease.rent_schedule.count() == 1:
        messages.error(request, _("A lease must keep at least one rent. Change it instead."))
    else:
        entry.delete()
        messages.success(request, _("Rent schedule entry removed."))
    return redirect(entry.lease)


# ---------------------------------------------------------------- calendar (iCalendar feed)

@login_required
def calendar_settings(request):
    feed, _created = CalendarFeed.objects.get_or_create(user=request.user)
    if request.method == "POST":
        if "regenerate" in request.POST:
            feed.regenerate()
            messages.success(request, _("A new calendar address has been made. The old one no longer works."))
        else:
            feed.include_all = request.POST.get("include_all") == "1"
            feed.save(update_fields=["include_all"])
            messages.success(request, _("Calendar settings saved."))
        return redirect("leases:calendar")
    url = request.build_absolute_uri(f"/calendar/{feed.token}.ics")
    return render(request, "leases/calendar.html", {"feed": feed, "feed_url": url,
                                                    "webcal_url": url.replace("https://", "webcal://", 1)
                                                    .replace("http://", "webcal://", 1)})


def _ics_escape(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """iCalendar lines must be folded at 75 octets."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def calendar_feed(request, token):
    """Read-only iCalendar feed of open lease events. The token in the address acts as the password."""
    feed = get_object_or_404(CalendarFeed.objects.select_related("user"), token=token)
    user = feed.user
    if not user.is_active or not has_role(user):
        return HttpResponse(status=404)
    events = LeaseEvent.objects.filter(status__in=workflow.OPEN).select_related("lease", "lease__counterparty")
    if not feed.include_all:
        events = events.filter(assigned_to=user)
    stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    host = request.get_host()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PHAEMA//Lease events//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_escape('PHAEMA lease events')}"]
    for e in events[:2000]:
        url = request.build_absolute_uri(e.get_absolute_url())
        end = e.due_date + timedelta(days=1)
        lines += [
            "BEGIN:VEVENT",
            f"UID:phaema-event-{e.pk}@{host}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{e.due_date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{_ics_escape(f'{e.display_title}: {e.lease.counterparty.name} ({e.lease.reference})')}",
            f"DESCRIPTION:{_ics_escape(f'{e.get_status_display()}. Open in PHAEMA: {url}')}",
            f"URL:{url}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    body = "\r\n".join(_fold(line) for line in lines) + "\r\n"
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="phaema-events.ics"'
    response["Cache-Control"] = "private, max-age=900"
    return response

