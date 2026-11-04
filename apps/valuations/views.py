# SPDX-License-Identifier: AGPL-3.0-or-later
"""Asset valuation pages."""
from collections import namedtuple
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core.models import ModuleSettings
from apps.core.roles import is_administrator, manages
from apps.properties.models import Property
from apps.reports.export import csv_response, xlsx_response

from . import programme, workflow
from .models import (AssetClass, AuditReview, Classification, Valuation, ValuationComponent, ValuationSettings,
                     Valuer)
from .seed import FROM_PURPOSE

Col = namedtuple("Col", "label type")


def valuation_view(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not ModuleSettings.load().valuation_enabled:
            return render(request, "valuations/off.html", status=404)
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def _can_work(user, prop):
    return is_administrator(user) or manages(user, prop)


def _date(text, default=None):
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        return default


def _staff():
    from django.contrib.auth import get_user_model

    from apps.core.roles import ADMINISTRATORS, SURVEYORS

    return (get_user_model().objects.filter(is_active=True, groups__name__in=(ADMINISTRATORS, SURVEYORS))
            .distinct().order_by("first_name", "username"))


def _assignee(choice):
    """'staff:12' or 'valuer:3' -> a Valuer (made for staff if needed), or None."""
    kind, _sep, pk = (choice or "").partition(":")
    if kind == "staff" and pk.isdigit():
        user = _staff().filter(pk=int(pk)).first()
        return workflow.staff_valuer(user) if user else None
    if kind == "valuer" and pk.isdigit():
        return Valuer.objects.filter(pk=int(pk), active=True).first()
    return None


def _assignees():
    return {"staff": _staff(), "externals": Valuer.objects.filter(active=True, status=Valuer.Status.EXTERNAL)}


def _year_end(request, settings):
    chosen = _date(request.GET.get("year") or request.POST.get("year"))
    return chosen or settings.year_end()


@valuation_view
def home(request):
    settings = ValuationSettings.load()
    year_end = _year_end(request, settings)
    admin = is_administrator(request.user)
    if request.method == "POST":
        if not admin:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "start":
            valuer = _assignee(request.POST.get("assignee"))
            _case, made = programme.start(year_end, request.user, valuer)
            if valuer is not None:
                for item in Valuation.objects.filter(valuation_date=year_end, valuer=valuer, case__isnull=False):
                    workflow.assign(item, valuer, request.user)
            messages.success(request, _("Programme started: %(n)s assets instructed, each with its own case.")
                             % {"n": made})
        elif action == "classify":
            made = _classify_from_purpose(_date(request.POST.get("from"), date.today()))
            messages.success(request, _("%(n)s properties classified from their holding purpose.") % {"n": made})
        elif action == "review":
            prop = get_object_or_404(Property, pk=request.POST.get("property"))
            prompt = next((p for p in programme.prompts() if p.property.pk == prop.pk), None)
            case = programme.open_review(prop, prompt.reasons if prompt else [], request.user)
            messages.success(request, _("Impairment review %(ref)s opened.") % {"ref": case.display_reference})
            return redirect(case)
        return redirect(f"{request.path}?year={year_end.isoformat()}")
    rows = programme.programme(year_end)
    started = Valuation.objects.filter(valuation_date=year_end).exists()
    counts = {s: 0 for s, _l in Valuation.Status.choices}
    for v in Valuation.objects.filter(valuation_date=year_end):
        counts[v.status] += 1
    classified = set(programme.current_classes().keys())
    unclassified = Property.objects.exclude(pk__in=classified).filter(parent__isnull=True).count()
    rotation = [(v, v.rotation_due(settings.rotation_years)) for v in Valuer.objects.filter(active=True)]
    audits = AuditReview.objects.exclude(status=AuditReview.Status.CLOSED)
    return render(request, "valuations/home.html", {
        "settings": settings, "year_end": year_end, "rows": rows, "started": started,
        "counts": [(n, dict(Valuation.Status.choices)[s]) for s, n in counts.items() if n],
        "prompts": programme.prompts(), "unclassified": unclassified, "is_admin": admin,
        "classes": AssetClass.objects.filter(active=True), "valuers": Valuer.objects.filter(active=True),
        "rotation": [(v, d) for v, d in rotation if d and d <= year_end],
        "years": [settings.year_end(date(date.today().year + n, 1, 1)) for n in (-2, -1, 0, 1)],
        "status_labels": dict(Valuation.Status.choices), **_assignees(),
        "mine": Valuation.objects.filter(valuer__user=request.user).exclude(status="accepted")
        .select_related("property"),
        "audit_open": audits.filter(status="open").count(), "audit_reported": audits.filter(status="reported").count(),
        "my_audits": audits.filter(assigned_to=request.user, status="open").select_related("valuation__property"),
    })


def _classify_from_purpose(effective):
    """Classify every top-level property that has no class yet, from its holding purpose."""
    classes = {c.code: c for c in AssetClass.objects.all()}
    have = set(Classification.objects.values_list("property_id", flat=True))
    made = 0
    for prop in Property.objects.filter(parent__isnull=True).exclude(pk__in=have):
        code = FROM_PURPOSE.get(prop.holding_purpose)
        if code and code in classes:
            Classification.objects.create(property=prop, asset_class=classes[code], effective_from=effective,
                                          reason="From the holding purpose in the property register")
            made += 1
    return made


# ------------------------------------------------------------------ a property

@valuation_view
def property_valuations(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    work = _can_work(request.user, prop)
    if request.method == "POST":
        if not work:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "classify":
            if not is_administrator(request.user):
                raise PermissionDenied
            cls = get_object_or_404(AssetClass, pk=request.POST.get("asset_class"))
            Classification.objects.create(property=prop, asset_class=cls,
                                          effective_from=_date(request.POST.get("from"), date.today()),
                                          reason=request.POST.get("reason", "").strip()[:200])
            messages.success(request, _("Classified as %(cls)s.") % {"cls": cls})
        elif action == "new":
            current = programme.current_class(prop)
            if current is None:
                messages.error(request, _("Classify the property first."))
                return redirect("valuations:property", pk=prop.pk)
            v = Valuation.objects.create(
                property=prop, asset_class=current.asset_class, basis=current.asset_class.basis,
                valuation_date=_date(request.POST.get("valuation_date"), ValuationSettings.load().year_end()),
                purpose=request.POST.get("purpose", "").strip()[:100] or "Financial statements (CIPFA Code)")
            return redirect(v)
        return redirect("valuations:property", pk=prop.pk)
    return render(request, "valuations/property.html", {
        "property": prop, "can_work": work, "is_admin": is_administrator(request.user),
        "classifications": prop.classifications.select_related("asset_class"),
        "current": programme.current_class(prop), "valuations": prop.valuations.select_related("valuer"),
        "classes": AssetClass.objects.filter(active=True), "today": date.today(),
        "year_end": ValuationSettings.load().year_end(),
    })


# ------------------------------------------------------------------ a valuation

class ValuationForm(forms.ModelForm):
    class Meta:
        model = Valuation
        fields = ["basis", "purpose", "terms_agreed_on", "valuation_date", "report_date", "inspection_date",
                  "inspection", "method", "value", "land_value", "building_value", "remaining_life",
                  "special_assumptions", "key_assumptions", "material_uncertainty", "uncertainty_statement",
                  "conflicts", "report", "notes"]
        widgets = {f: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
                   for f in ("terms_agreed_on", "valuation_date", "report_date", "inspection_date")}
        widgets.update({f: forms.Textarea(attrs={"rows": 3})
                        for f in ("special_assumptions", "key_assumptions", "uncertainty_statement", "conflicts",
                                  "notes")})

    def clean(self):
        data = super().clean()
        if data.get("material_uncertainty") and not (data.get("uncertainty_statement") or "").strip():
            self.add_error("uncertainty_statement", "Give the valuer's statement of material uncertainty.")
        land, building, value = data.get("land_value"), data.get("building_value"), data.get("value")
        if value is not None and land is not None and building is not None and land + building != value:
            self.add_error("building_value", "Land and buildings must add up to the value.")
        return data


@valuation_view
def valuation_detail(request, pk):
    v = get_object_or_404(Valuation.objects.select_related("property", "asset_class", "valuer", "case"), pk=pk)
    work = workflow.can_work(request.user, v)
    editable = work and v.status != Valuation.Status.ACCEPTED
    form = ValuationForm(instance=v) if editable else None
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "accept":
            if not is_administrator(request.user):
                raise PermissionDenied
            problems = _acceptance_problems(v)
            if problems:
                for p in problems:
                    messages.error(request, p)
            else:
                v.status, v.accepted_by, v.accepted_on = Valuation.Status.ACCEPTED, request.user, date.today()
                v.save(update_fields=["status", "accepted_by", "accepted_on", "updated_at"])
                messages.success(request, _("Accepted for the accounts."))
            return redirect(v)
        if action in ("assign", "flag", "audit_report", "audit_close"):
            _audit_or_assign(request, v, action)
            return redirect(v)
        if action == "reopen" and is_administrator(request.user):
            v.status, v.accepted_by, v.accepted_on = Valuation.Status.RECEIVED, None, None
            v.save(update_fields=["status", "accepted_by", "accepted_on", "updated_at"])
            return redirect(v)
        if not editable:
            raise PermissionDenied
        if action == "return":
            v.status = Valuation.Status.REJECTED
            v.notes = (v.notes + "\n" if v.notes else "") + f"Returned {date.today():%d/%m/%Y}: " + \
                request.POST.get("comments", "").strip()
            v.save(update_fields=["status", "notes", "updated_at"])
            return redirect(v)
        if action == "component":
            try:
                value = Decimal(request.POST.get("value", "").replace(",", "").replace("£", ""))
            except InvalidOperation:
                messages.error(request, _("Enter the component's value."))
                return redirect(v)
            life = request.POST.get("useful_life", "")
            from apps.maintenance.models import Component

            ValuationComponent.objects.create(
                valuation=v, name=request.POST.get("name", "").strip()[:150] or "Component", value=value,
                useful_life=int(life) if life.isdigit() else None,
                component=Component.objects.filter(pk=request.POST.get("component") or 0, property=v.property).first())
            return redirect(v)
        if action == "remove_component":
            v.components.filter(pk=request.POST.get("item")).delete()
            return redirect(v)
        form = ValuationForm(request.POST, request.FILES, instance=v)
        if form.is_valid():
            v = form.save(commit=False)
            if v.status in (Valuation.Status.INSTRUCTED, Valuation.Status.REJECTED) and v.value is not None:
                v.status = Valuation.Status.RECEIVED
            v.save()
            messages.success(request, _("Valuation saved."))
            return redirect(v)
    settings = ValuationSettings.load()
    previous = v.previous()
    needs_components = bool(v.building_value and v.building_value > settings.component_threshold)
    try:
        from apps.maintenance.models import Component

        components = Component.objects.filter(property=v.property)
    except LookupError:
        components = []
    return render(request, "valuations/valuation.html", {
        "v": v, "form": form, "can_work": work, "editable": editable, "is_admin": is_administrator(request.user),
        "previous": previous, "change": (v.value - previous.value) if previous and v.value is not None
        and previous.value is not None else None, "settings": settings, "needs_components": needs_components,
        "problems": _acceptance_problems(v) if v.status != Valuation.Status.ACCEPTED else [],
        "register_components": components, **_assignees(),
        "can_assign": is_administrator(request.user) or _can_work(request.user, v.property),
        "audits": [(a, workflow.can_respond(request.user, a)) for a in v.audit_reviews.select_related(
            "assigned_to", "reported_by", "closed_by")],
        "audit_reasons": AuditReview._meta.get_field("reason").choices, "outcomes": AuditReview.Outcome.choices,
        "accounts_year": workflow.accounts_year(v.valuation_date), "today": date.today(),
    })


def _audit_or_assign(request, v, action):
    post = request.POST
    if action == "assign":
        if not (is_administrator(request.user) or _can_work(request.user, v.property)):
            raise PermissionDenied
        valuer = _assignee(post.get("assignee"))
        if valuer is None:
            messages.error(request, _("Choose a member of staff or an external valuer."))
            return
        workflow.assign(v, valuer, request.user)
        messages.success(request, _("Assigned to %(who)s.") % {"who": valuer})
    elif action == "flag":
        if not is_administrator(request.user):
            raise PermissionDenied
        if not post.get("query", "").strip():
            messages.error(request, _("Enter the auditor's query, or why it is flagged."))
            return
        from django.contrib.auth import get_user_model

        assigned = get_user_model().objects.filter(pk=post.get("assigned_to") or 0).first()
        workflow.flag(v, request.user, post["query"], post.get("reason", "sample"), post.get("auditor", "").strip(),
                      _date(post.get("due_on")), assigned)
        messages.success(request, _("Flagged for audit."))
    else:
        review = get_object_or_404(AuditReview, pk=post.get("review"), valuation=v)
        if action == "audit_report":
            if not workflow.can_respond(request.user, review):
                raise PermissionDenied
            if not post.get("response", "").strip():
                messages.error(request, _("Write the response to the auditor."))
                return
            workflow.report(review, request.user, post["response"], request.FILES.get("evidence"),
                            _date(post.get("reported_on"), date.today()))
            messages.success(request, _("Response recorded as reported to the auditor."))
        else:
            if not is_administrator(request.user):
                raise PermissionDenied
            outcome = post.get("outcome")
            if outcome not in AuditReview.Outcome.values:
                messages.error(request, _("Choose the outcome."))
                return
            workflow.close(review, request.user, outcome, post.get("notes", ""))
            messages.success(request, _("Audit closed.") if outcome != "amended" else
                             _("Audit closed. The valuation is reopened for amendment."))


def _acceptance_problems(v):
    out = []
    if v.value is None:
        out.append(_("Enter the value."))
    if v.valuer_id is None:
        out.append(_("Record the valuer."))
    if not v.report_date:
        out.append(_("Record the report date."))
    if not v.terms_agreed_on:
        out.append(_("Record when the terms of engagement were agreed."))
    if not v.split_ok():
        out.append(_("Land and buildings do not add up to the value."))
    if v.material_uncertainty and not v.uncertainty_statement.strip():
        out.append(_("Add the statement of material uncertainty."))
    settings = ValuationSettings.load()
    if v.building_value and v.building_value > settings.component_threshold and not v.components.exists():
        out.append(_("The buildings are worth more than the componentisation threshold: add the significant "
                     "components."))
    return out


# ------------------------------------------------------------------ audit

AUDIT_COLUMNS = [Col("Asset reference", "text"), Col("Asset", "text"), Col("Valuation date", "date"),
                 Col("Value", "money"), Col("Basis", "text"), Col("Valuer", "text"), Col("Why flagged", "text"),
                 Col("Auditor", "text"), Col("Query", "text"), Col("Response due", "date"),
                 Col("Prepared by", "text"), Col("Status", "text"), Col("Response", "text"),
                 Col("Reported", "date"), Col("Outcome", "text"), Col("Closed", "date")]


@valuation_view
def audit(request):
    years = sorted(set(AuditReview.objects.values_list("accounts_year", flat=True)), reverse=True)
    year = request.GET.get("year") or (years[0] if years else "")
    qs = AuditReview.objects.filter(accounts_year=year).select_related(
        "valuation__property", "valuation__valuer", "assigned_to")
    if request.GET.get("format") in ("xlsx", "csv"):
        data = [[a.valuation.property.reference, a.valuation.property.name, a.valuation.valuation_date,
                 a.valuation.value, a.valuation.get_basis_display(), str(a.valuation.valuer or ""),
                 a.get_reason_display(), a.auditor, a.query, a.due_on,
                 (a.assigned_to.get_full_name() or a.assigned_to.username) if a.assigned_to else "",
                 a.get_status_display(), a.response, a.reported_on, a.get_outcome_display() if a.outcome else "",
                 a.closed_on] for a in qs]
        title = f"Valuation audit log {year}"
        return csv_response(title, AUDIT_COLUMNS, data) if request.GET["format"] == "csv" else \
            xlsx_response(title, AUDIT_COLUMNS, data)
    groups = [(label, [a for a in qs if a.status == value]) for value, label in AuditReview.Status.choices]
    return render(request, "valuations/audit.html", {"year": year, "years": years, "groups": groups,
                                                     "today": date.today()})


# ------------------------------------------------------------------ downloads

SCHEDULE_COLUMNS = [Col("Asset reference", "text"), Col("Name", "text"), Col("UPRN", "text"),
                    Col("Asset class", "text"), Col("Basis", "text"), Col("Valuation date", "date"),
                    Col("Valuer", "text"), Col("Internal or external", "text"), Col("Value", "money"),
                    Col("Land", "money"), Col("Buildings", "money"), Col("Remaining life (years)", "number"),
                    Col("Material uncertainty", "text"), Col("Status", "text"), Col("Components", "text")]


@valuation_view
def schedule(request):
    settings = ValuationSettings.load()
    year_end = _year_end(request, settings)
    data = []
    for prop, cls, v in programme.schedule(year_end):
        data.append([prop.reference, prop.name, prop.uprn, cls.name,
                     v.get_basis_display() if v else cls.get_basis_display(), v.valuation_date if v else None,
                     str(v.valuer) if v and v.valuer else "", v.valuer.get_status_display() if v and v.valuer else "",
                     v.value if v else None, v.land_value if v else None, v.building_value if v else None,
                     v.remaining_life if v else None, ("Yes" if v.material_uncertainty else "No") if v else "",
                     "Accepted" if v else "Not valued",
                     "; ".join(f"{c.name} £{c.value:,.0f} ({c.useful_life or '?'} yrs)" for c in v.components.all())
                     if v else ""])
    title = f"Asset valuations at {year_end:%d %B %Y}"
    fmt = request.GET.get("format", "xlsx")
    return csv_response(title, SCHEDULE_COLUMNS, data) if fmt == "csv" else \
        xlsx_response(title, SCHEDULE_COLUMNS, data, totals=True)


PACK_COLUMNS = [Col("Asset reference", "text"), Col("Name", "text"), Col("Address", "text"), Col("Postcode", "text"),
                Col("UPRN", "text"), Col("Asset class", "text"), Col("Basis", "text"), Col("Tenure", "text"),
                Col("Occupation", "text"), Col("GIA m²", "number"), Col("NIA m²", "number"),
                Col("Site area ha", "number"), Col("Measurement basis", "text"), Col("Current rent £", "money"),
                Col("Leases", "text"), Col("Last valuation date", "date"), Col("Last value", "money"),
                Col("Why it is due", "text")]


@valuation_view
def data_pack(request):
    """The valuer's instructions: every asset due, with what PHAEMA knows about it (VA-10)."""
    from apps.leases.models import Lease

    settings = ValuationSettings.load()
    year_end = _year_end(request, settings)
    data = []
    for due in programme.programme(year_end):
        p = due.property
        leases = Lease.objects.filter(properties__in=[p.pk] + list(p._descendant_ids()), direction="out",
                                      status__in=("current", "holding_over")).distinct().select_related("counterparty")
        rent = sum((lease.annual_rent or 0 for lease in leases), Decimal("0"))
        data.append([p.reference, p.name, ", ".join(x for x in (p.address_line_1, p.town) if x), p.postcode, p.uprn,
                     due.asset_class.name, due.asset_class.get_basis_display(),
                     p.get_tenure_display() if p.tenure else "", p.get_occupation_display() if p.occupation else "",
                     p.gia_sqm, p.nia_sqm, p.site_area_ha, p.get_area_standard_display() if p.area_standard else "",
                     rent or None, "; ".join(f"{lease.reference} {lease.counterparty}, £{lease.annual_rent or 0:,.0f}"
                                             f"{', ends ' + lease.term_end.strftime('%d/%m/%Y') if lease.term_end else ''}"
                                             for lease in leases),
                     due.last.valuation_date if due.last else None, due.last.value if due.last else None, due.reason])
    title = f"Valuation instructions {year_end:%d %B %Y}"
    return xlsx_response(title, PACK_COLUMNS, data)
