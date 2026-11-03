# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from apps.core.models import AuditEntry

from .models import Property, Title

# Sortable columns: URL key -> (heading, database ordering)
SORT_COLUMNS = {
    "reference": (_("Reference"), ["reference"]),
    "name": (_("Name"), ["name", "reference"]),
    "type": (_("Type"), ["property_type", "reference"]),
    "purpose": (_("Purpose"), ["holding_purpose", "reference"]),
    "occupation": (_("Occupation"), ["occupation", "reference"]),
    "postcode": (_("Postcode"), ["postcode", "reference"]),
    "nia": (_("NIA m²"), ["nia_sqm", "reference"]),
    "surveyor": (_("Managed by"), ["managing_surveyor__first_name", "managing_surveyor__last_name",
                                   "managing_surveyor__username", "reference"]),
}


def display_name(user):
    return (user.get_full_name() or user.username) if user else ""


class PropertyListView(LoginRequiredMixin, ListView):
    model = Property
    paginate_by = 50
    template_name = "properties/property_list.html"

    FILTERS = ("property_type", "holding_purpose", "occupation", "tenure")

    def get_queryset(self):
        qs = Property.objects.select_related("parent", "managing_surveyor")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(reference__icontains=q) | Q(name__icontains=q) | Q(uprn=q)
                | Q(address_line_1__icontains=q) | Q(town__icontains=q)
                | Q(postcode__icontains=q) | Q(titles__title_number__iexact=q.replace(" ", ""))
            ).distinct()
        for f in self.FILTERS:
            value = self.request.GET.get(f)
            if value:
                qs = qs.filter(**{f: value})
        surveyor = self.request.GET.get("surveyor", "")
        if surveyor == "me":
            qs = qs.filter(managing_surveyor=self.request.user)
        elif surveyor == "none":
            qs = qs.filter(managing_surveyor__isnull=True)
        elif surveyor.isdigit():
            qs = qs.filter(managing_surveyor_id=int(surveyor))
        sort, descending = self._sort()
        ordering = SORT_COLUMNS[sort][1]
        if descending:
            ordering = [f"-{o}" for o in ordering]
        return qs.order_by(*ordering)

    def _sort(self):
        raw = self.request.GET.get("sort", "reference")
        descending = raw.startswith("-")
        key = raw.lstrip("-")
        return (key, descending) if key in SORT_COLUMNS else ("reference", False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        get = self.request.GET
        ctx["q"] = get.get("q", "")
        ctx["filters"] = [
            (f, Property._meta.get_field(f).verbose_name, Property._meta.get_field(f).choices, get.get(f, ""))
            for f in self.FILTERS
        ]
        User = get_user_model()
        surveyors = User.objects.filter(is_active=True).filter(
            Q(managed_properties__isnull=False) | Q(is_staff=True)
        ).distinct().order_by("first_name", "last_name", "username")
        ctx["surveyor_options"] = [("me", _("My properties")), ("none", _("Unassigned"))] + [
            (str(u.pk), display_name(u)) for u in surveyors
        ]
        ctx["surveyor_selected"] = get.get("surveyor", "")

        # Column headings with sort links that keep the current filters.
        sort, descending = self._sort()
        base = get.copy()
        base.pop("page", None)
        headings = []
        for key, (label, _ordering) in SORT_COLUMNS.items():
            params = base.copy()
            active = key == sort
            params["sort"] = f"-{key}" if active and not descending else key
            headings.append({
                "label": label,
                "url": "?" + params.urlencode(),
                "aria_sort": ("descending" if descending else "ascending") if active else "none",
                "numeric": key == "nia",
            })
        ctx["headings"] = headings
        ctx["querystring"] = base.urlencode()
        return ctx


class PropertyDetailView(LoginRequiredMixin, DetailView):
    model = Property
    template_name = "properties/property_detail.html"

    def get_queryset(self):
        return Property.objects.select_related("parent", "managing_surveyor").prefetch_related("photos")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["children"] = obj.children.all()
        ctx["titles"] = obj.titles.prefetch_related("documents")
        ctx["photos"] = list(obj.photos.all())
        ctx["breakdown"] = obj.area_breakdown()
        ctx["surveyor_name"] = display_name(obj.managing_surveyor)
        ctx["history"] = AuditEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Property), object_id=str(obj.pk)
        ).select_related("user")[:20]
        return ctx


class TitleDetailView(LoginRequiredMixin, DetailView):
    model = Title
    template_name = "properties/title_detail.html"

    def get_queryset(self):
        return Title.objects.prefetch_related("properties", "documents")
