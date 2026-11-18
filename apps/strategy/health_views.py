# SPDX-License-Identifier: AGPL-3.0-or-later
"""The annual asset management health check: start, answer, note, finish, report."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from apps.core.roles import has_role, is_administrator
from apps.projects.models import financial_year_label

from . import health
from .models import Action, EstateStrategy, HealthAnswer, HealthCheck, HealthNote, HealthQuestion, Objective


def can_answer(user, check):
    """The lead and administrators, while the check is in progress."""
    return check.status == HealthCheck.Status.DRAFT and (is_administrator(user) or check.lead_id == user.pk)


def _require_role(user):
    if not has_role(user):
        raise PermissionDenied


@login_required
def health_list(request):
    _require_role(request.user)
    from .views import _people

    year = health.current_year()
    checks = list(HealthCheck.objects.select_related("lead"))
    rows = [(c, health.counts(c)) for c in checks]
    if request.method == "POST":
        if not is_administrator(request.user):
            raise PermissionDenied
        lead = _people().filter(pk=request.POST.get("lead") or 0).first() or request.user
        check = health.start(lead, year)
        messages.success(request, _("The %(year)s health check has started.") % {"year": financial_year_label(year)})
        return redirect(check)
    return render(request, "strategy/health_list.html", {
        "rows": rows, "year_label": financial_year_label(year), "is_admin": is_administrator(request.user),
        "started": any(c.year == year for c in checks), "people": _people(), "credit": health.CREDIT,
        "questions": HealthQuestion.objects.filter(active=True).count()})


def _save_heading(request, check, heading):
    today = date.today()
    changed = 0
    for a in check.answers.filter(heading=heading):
        answer = request.POST.get(f"answer-{a.pk}", a.answer)
        if answer not in ("", *HealthAnswer.Answer.values):
            answer = a.answer
        notes = request.POST.get(f"notes-{a.pk}", a.notes).strip()
        evidence = request.POST.get(f"evidence-{a.pk}", a.evidence).strip()
        if (answer, notes, evidence) != (a.answer, a.notes, a.evidence):
            a.answer, a.notes, a.evidence = answer, notes, evidence
            a.answered_by, a.answered_on = request.user, today
            a.save()
            changed += 1
    return changed


def _add_action(request, check):
    a = get_object_or_404(HealthAnswer, pk=request.POST.get("answer") or 0, health_check=check)
    objective = get_object_or_404(Objective, pk=request.POST.get("objective") or 0)
    title = (request.POST.get("title") or "").strip() or f"Health check: {a.wording}"
    action = Action.objects.create(objective=objective, title=title[:200], owner=check.lead,
                                   notes=f"From the {financial_year_label(check.year)} health check"[:255])
    a.action = action
    a.save(update_fields=["action"])
    return action


@login_required
def health_check(request, pk):
    _require_role(request.user)
    check = get_object_or_404(HealthCheck.objects.select_related("lead"), pk=pk)
    answering = can_answer(request.user, check)
    if request.method == "POST":
        what = request.POST.get("action")
        if what == "note":
            text = (request.POST.get("text") or "").strip()
            answer = check.answers.filter(pk=request.POST.get("answer") or 0).first()
            if text:
                HealthNote.objects.create(health_check=check, answer=answer, author=request.user, text=text)
                messages.success(request, _("Note added."))
            return redirect(check.get_absolute_url() + (f"#q{answer.pk}" if answer else "#notes"))
        if what == "reopen":
            if not is_administrator(request.user):
                raise PermissionDenied
            check.status, check.finished_on = HealthCheck.Status.DRAFT, None
            check.save()
            return redirect(check)
        if not answering:
            raise PermissionDenied
        if what == "save":
            heading = request.POST.get("heading", "")
            n = _save_heading(request, check, heading)
            messages.success(request, _("Saved.") if n else _("No changes to save."))
            return redirect(check.get_absolute_url() + f"#h-{heading}")
        if what == "add_action":
            action = _add_action(request, check)
            messages.success(request, _("Added to the action plan: %(action)s") % {"action": action.label})
            return redirect(check.get_absolute_url() + f"#q{request.POST.get('answer')}")
        if what == "finish":
            check.summary = (request.POST.get("summary") or "").strip()
            check.status, check.finished_on = HealthCheck.Status.FINISHED, date.today()
            check.save()
            messages.success(request, _("The health check is finished."))
            return redirect(check)
        if what == "summary":
            check.summary = (request.POST.get("summary") or "").strip()
            check.save(update_fields=["summary", "updated_at"])
            return redirect(check.get_absolute_url() + "#finish")
    strategy = EstateStrategy.current()
    prev = check.previous()
    return render(request, "strategy/health_check.html", {
        "check": check, "sections": health.sections(check), "counts": health.counts(check), "previous": prev,
        "previous_label": financial_year_label(prev.year) if prev else "", "answering": answering,
        "is_admin": is_administrator(request.user), "choices": HealthAnswer.Answer.choices,
        "objectives": list(strategy.objectives.all()) if strategy else [], "strategy": strategy,
        "change_labels": health.SCORE_LABELS, "general_notes": check.notes.filter(answer=None).select_related(
            "author"), "credit": health.CREDIT, "year_label": financial_year_label(check.year)})


@login_required
def health_report(request, pk):
    _require_role(request.user)
    check = get_object_or_404(HealthCheck, pk=pk)
    from apps.documents import merge
    from apps.documents import render as doc_render

    text = health.build_report(check, request.user)
    if request.GET.get("format") == "docx":
        from types import SimpleNamespace

        data = doc_render.to_docx(SimpleNamespace(letterhead=True, prescribed_form=""), text,
                                  merge.context(user=request.user))
        response = HttpResponse(
            data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response["Content-Disposition"] = (
            f'attachment; filename="Asset management health check {financial_year_label(check.year).replace("/", "-")}.docx"')
        return response
    return render(request, "strategy/health_report.html", {
        "check": check, "body": mark_safe(doc_render.to_html(text, merge.context(user=request.user)))})  # noqa: S308
