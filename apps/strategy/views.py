# SPDX-License-Identifier: AGPL-3.0-or-later
"""The estate strategy, its objectives and action plan, and the board report."""
import re
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.core.roles import ADMINISTRATORS, SURVEYORS, is_administrator

from . import progress, report
from .models import Action, EstateStrategy, Objective


def can_update(user, objective):
    """Administrators set the strategy; an objective's owner keeps it up to date."""
    return is_administrator(user) or (objective.owner_id is not None and objective.owner_id == user.pk)


def _strategy(request):
    pk = request.GET.get("strategy", "")
    if pk.isdigit():
        return get_object_or_404(EstateStrategy, pk=pk)
    return EstateStrategy.current() or EstateStrategy.objects.first()


@login_required
def home(request):
    strategy = _strategy(request)
    states = [progress.objective_state(o, request.user) for o in strategy.objectives.select_related("owner")] \
        if strategy else []
    return render(request, "strategy/home.html", {
        "strategy": strategy, "objectives": states, "others": EstateStrategy.objects.exclude(
            pk=strategy.pk if strategy else None),
        "is_admin": is_administrator(request.user), "rag_tag": progress.RAG_TAG, "rag_words": progress.RAG_WORDS,
        "principles": [p.strip() for p in (strategy.principles if strategy else "").split("\n") if p.strip()],
    })


def _people():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(is_active=True, groups__name__in=[ADMINISTRATORS, SURVEYORS]) \
        .distinct().order_by("first_name", "last_name", "username")


def _find_link(text):
    """A project or case from its reference, for example PRJ-2026-001 or CAS-2026-0058."""
    from apps.cases.models import Case
    from apps.projects.models import Project

    m = re.match(r"^\s*(PRJ|CAS)-(\d{4})-0*(\d+)", text.upper())
    if not m:
        return None, None
    kind, year, number = m.group(1), int(m.group(2)), int(m.group(3))
    model = Project if kind == "PRJ" else Case
    return kind, model.objects.filter(year=year, number=number).first()


@login_required
def objective(request, pk):
    obj = get_object_or_404(Objective.objects.select_related("strategy", "owner", "status_by"), pk=pk)
    editable = can_update(request.user, obj)
    if request.method == "POST":
        _act(request, obj, editable)
        return redirect(obj)
    state = progress.objective_state(obj, request.user)
    return render(request, "strategy/objective.html", {
        "objective": obj, "state": state, "can_update": editable, "people": _people(),
        "rag_choices": Objective.Rag.choices, "action_statuses": Action.Status.choices,
        "rag_tag": progress.RAG_TAG, "rag_words": progress.RAG_WORDS, "today": date.today(),
        "can_change_action": {s.action.pk for s in state.actions
                              if editable or s.action.owner_id == request.user.pk},
    })


def _date(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _act(request, obj, editable):
    post = request.POST
    action = post.get("action", "")
    if action == "action_status":
        item = get_object_or_404(Action, pk=post.get("item", 0), objective=obj)
        if not (editable or item.owner_id == request.user.pk) or item.project_id or item.case_id:
            raise PermissionDenied
        if post.get("status") in Action.Status.values:
            item.status = post["status"]
            item.save()
            messages.success(request, _("Action updated."))
        return
    if not editable:
        raise PermissionDenied
    if action == "status":
        if post.get("reported_status", "") not in [*Objective.Rag.values, ""]:
            return
        obj.reported_status = post.get("reported_status", "")
        obj.progress_note = post.get("progress_note", "").strip()
        obj.status_on, obj.status_by = date.today(), request.user
        obj.save(update_fields=["reported_status", "progress_note", "status_on", "status_by", "updated_at"])
        messages.success(request, _("Status and progress saved."))
    elif action == "add":
        link = post.get("link", "").strip()
        item = Action(objective=obj, title=post.get("title", "").strip()[:200],
                      target_date=_date(post.get("target_date")), notes=post.get("notes", "").strip()[:255])
        owner = post.get("owner", "")
        if owner.isdigit():
            item.owner = _people().filter(pk=int(owner)).first()
        if link:
            kind, found = _find_link(link)
            if found is None:
                messages.error(request, _("No project or case with the reference %(r)s. Use a reference such as "
                                          "PRJ-2026-001 or CAS-2026-0058.") % {"r": link})
                return
            if kind == "PRJ":
                from apps.projects import rules

                if not rules.can_see(request.user, found):
                    messages.error(request, _("No project or case with the reference %(r)s.") % {"r": link})
                    return
                item.project = found
            else:
                item.case = found
        if not (item.title or item.project_id or item.case_id):
            messages.error(request, _("Describe the action, or give a project or case reference."))
            return
        item.save()
        messages.success(request, _("Added to the action plan."))
    elif action == "remove":
        get_object_or_404(Action, pk=post.get("item", 0), objective=obj).delete()
        messages.success(request, _("Removed from the action plan."))


@login_required
def board_report(request):
    strategy = _strategy(request)
    if strategy is None:
        return redirect("strategy:home")
    from apps.documents import merge
    from apps.documents import render as doc_render

    text = report.build(strategy, user=request.user)
    if request.GET.get("format") == "docx":
        from types import SimpleNamespace

        data = doc_render.to_docx(SimpleNamespace(letterhead=True, prescribed_form=""), text,
                                  merge.context(user=request.user))
        response = HttpResponse(
            data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        name = f"Estate strategy progress {date.today():%Y-%m-%d}"
        response["Content-Disposition"] = f'attachment; filename="{name}.docx"'
        return response
    return render(request, "strategy/report.html", {
        "strategy": strategy, "body": mark_safe(doc_render.to_html(text, merge.context(user=request.user)))})  # noqa: S308
