# SPDX-License-Identifier: AGPL-3.0-or-later
"""Site visits (the visit sheet, level B): start a visit, fill it in on the phone with photos, finish it."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from apps.core.roles import has_role, is_administrator

from . import visit as v
from . import workflow
from .models import Case, CaseNote, SiteVisit, SiteVisitPhoto


def can_fill_in(user, visit):
    """The case owner, the property's managing surveyor and administrators, while the visit is in progress."""
    return not visit.is_finished and workflow.can_work(user, visit.case)


def _case(pk):
    return get_object_or_404(Case.objects.select_related("case_type", "property", "lease", "owner"), pk=pk)


@login_required
def visit_start(request, pk):
    case = _case(pk)
    if request.method != "POST" or not workflow.can_work(request.user, case):
        raise PermissionDenied
    visit = v.start_visit(case, request.user)
    if visit is None:
        raise Http404("This case is not about a property.")
    messages.success(request, _("Visit started. Answer each section and save it as you go."))
    return redirect(visit)


def _add_photos(request, visit):
    from apps.core.files import validate_image
    from apps.properties.models import PropertyPhoto

    answer = visit.answers.filter(pk=request.POST.get("answer") or 0).first()
    caption = (request.POST.get("caption") or "").strip()[:200]
    to_property = bool(request.POST.get("to_property"))
    added, problems = 0, []
    for upload in request.FILES.getlist("photos")[:20]:
        try:
            validate_image(upload)
        except ValidationError as exc:
            problems.append(f"{upload.name}: {exc.messages[0]}")
            continue
        photo = SiteVisitPhoto(visit=visit, answer=answer, image=upload,
                               caption=caption or (answer.label if answer else ""), created_by=request.user)
        photo.save()
        if to_property:
            target = (answer.building if answer and answer.building_id else visit.property)
            copy = PropertyPhoto(property=target, caption=photo.caption, taken_on=visit.visited_on,
                                 created_by=request.user)
            from django.core.files.base import ContentFile

            with photo.image.open("rb") as handle:
                copy.image.save("photo.jpg", ContentFile(handle.read()), save=True)
            photo.property_photo = copy
            photo.save(update_fields=["property_photo"])
        added += 1
    return added, problems


@login_required
def visit_page(request, pk, visit_pk):
    case = _case(pk)
    if not has_role(request.user):
        raise PermissionDenied
    visit = get_object_or_404(SiteVisit.objects.select_related("property", "visited_by"), pk=visit_pk, case=case)
    filling = can_fill_in(request.user, visit)
    if request.method == "POST":
        what = request.POST.get("action")
        if what == "reopen":
            if not is_administrator(request.user):
                raise PermissionDenied
            visit.status, visit.finished_on = SiteVisit.Status.DRAFT, None
            visit.save()
            return redirect(visit)
        if not filling:
            raise PermissionDenied
        if what == "section":
            key = request.POST.get("section", "")
            now = timezone.now()
            changed = 0
            for a in visit.answers.all():
                if str(a.building_id or 0) != key:
                    continue
                value = v.answer_from(request.POST, a)
                note = (request.POST.get(f"n{a.pk}") or "").strip()[:500]
                if (value, note) != (a.value, a.note):
                    a.value, a.note, a.answered_at = value, note, now
                    a.save(update_fields=["value", "note", "answered_at"])
                    changed += 1
            messages.success(request, _("Saved.") if changed else _("No changes to save."))
            return redirect(visit.get_absolute_url() + f"#s{key}")
        if what == "details":
            for field in ("time", "weather", "people_met", "notes", "follow_up"):
                setattr(visit, field, (request.POST.get(field) or "").strip())
            try:
                visit.visited_on = date.fromisoformat(request.POST.get("visited_on") or "")
            except ValueError:
                pass
            visit.save()
            messages.success(request, _("Saved."))
            return redirect(visit.get_absolute_url() + "#details")
        if what == "photos":
            added, problems = _add_photos(request, visit)
            for p in problems:
                messages.error(request, p)
            if added:
                messages.success(request, _("%(n)s photo(s) added.") % {"n": added})
            return redirect(visit.get_absolute_url() + "#photos")
        if what == "delete_photo":
            photo = get_object_or_404(SiteVisitPhoto, pk=request.POST.get("photo") or 0, visit=visit)
            photo.image.delete(save=False)
            photo.delete()
            return redirect(visit.get_absolute_url() + "#photos")
        if what == "finish":
            visit.status, visit.finished_on = SiteVisit.Status.FINISHED, date.today()
            visit.save()
            answered, total = v.progress(visit)
            CaseNote.objects.create(case=case, created_by=request.user, text=(
                f"Site visit on {visit.visited_on:%d %B %Y} by "
                f"{visit.visited_by.get_full_name() or visit.visited_by.username if visit.visited_by else 'unknown'} "
                f"finished: {answered} of {total} checklist items answered, {visit.photos.count()} photos."))
            messages.success(request, _("The visit is finished and noted on the case."))
            return redirect(visit)
    if not filling:
        return redirect("cases:visit-record", case.pk, visit.pk)
    answered, total = v.progress(visit)
    return render(request, "cases/visit.html", {
        "case": case, "visit": visit, "sections": v.visit_sections(visit), "filling": filling,
        "answered": answered, "total": total, "photos": visit.photos.select_related("answer"),
        "is_admin": is_administrator(request.user)})


@login_required
def visit_record(request, pk, visit_pk):
    from types import SimpleNamespace

    from apps.documents import merge
    from apps.documents import render as doc_render

    case = _case(pk)
    if not has_role(request.user):
        raise PermissionDenied
    visit = get_object_or_404(SiteVisit, pk=visit_pk, case=case)
    text = v.build_record(visit, request.user)
    values = merge.context(user=request.user, case=case, prop=visit.property)
    if request.GET.get("format") == "docx":
        data = doc_render.to_docx(SimpleNamespace(letterhead=True, prescribed_form=""), text, values)
        response = HttpResponse(
            data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response["Content-Disposition"] = (
            f'attachment; filename="Site visit {case.reference} {visit.visited_on:%Y-%m-%d}.docx"')
        return response
    return render(request, "cases/visit_record.html", {
        "case": case, "visit": visit, "body": mark_safe(doc_render.to_html(text, values)),  # noqa: S308
        "photos": visit.photos.select_related("answer"), "can_fill_in": can_fill_in(request.user, visit),
        "is_admin": is_administrator(request.user)})
