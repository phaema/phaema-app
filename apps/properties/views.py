# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.views.generic import DetailView, ListView

from apps.core.models import AuditEntry

from .models import Property


class PropertyListView(LoginRequiredMixin, ListView):
    model = Property
    paginate_by = 50
    template_name = "properties/property_list.html"

    FILTERS = ("property_type", "holding_purpose", "occupation", "tenure")

    def get_queryset(self):
        qs = Property.objects.select_related("parent")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(reference__icontains=q) | Q(name__icontains=q) | Q(uprn=q)
                | Q(address_line_1__icontains=q) | Q(town__icontains=q)
                | Q(postcode__icontains=q.replace(" ", "")) | Q(postcode__icontains=q)
                | Q(titles__title_number__iexact=q.replace(" ", ""))
            ).distinct()
        for f in self.FILTERS:
            value = self.request.GET.get(f)
            if value:
                qs = qs.filter(**{f: value})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["filters"] = [
            (f, Property._meta.get_field(f).verbose_name, Property._meta.get_field(f).choices,
             self.request.GET.get(f, ""))
            for f in self.FILTERS
        ]
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class PropertyDetailView(LoginRequiredMixin, DetailView):
    model = Property
    template_name = "properties/property_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["children"] = obj.children.all()
        ctx["titles"] = obj.titles.all()
        ctx["history"] = AuditEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Property), object_id=str(obj.pk)
        ).select_related("user")[:20]
        return ctx
