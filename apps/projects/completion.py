# SPDX-License-Identifier: AGPL-3.0-or-later
"""The completion checklist: what the register needs once a project completes. PHAEMA prompts and links to the
right form, already filled in from the project; it never changes the register by itself."""
from dataclasses import dataclass
from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import gettext as _

from .models import PHASE_ORDER, Phase, ProjectProperty, ProjectType


@dataclass
class Step:
    key: str
    text: str
    url: str = ""
    link_text: str = ""
    done: bool = False
    automatic: bool = False  # PHAEMA checks it; nobody ticks it


def shown(project):
    """The checklist appears once delivery is under way, so the team can see what completion will need."""
    return PHASE_ORDER.index(project.phase) >= PHASE_ORDER.index(Phase.DELIVERY)


def _admin(view, *args, **params):
    url = reverse(f"admin:properties_{view}", args=args)
    return f"{url}?{urlencode(params)}" if params else url


def steps(project, user):
    from apps.core.access import can_use

    kind = project.project_type.kind
    links = list(project.property_links.select_related("property"))
    ticked = set(project.completion_steps.values_list("key", flat=True))
    out = []

    def manual(key, text, url="", link_text=""):
        out.append(Step(key, text, url, link_text, done=key in ticked))

    first_line = (project.site_address or "").splitlines()[0] if project.site_address else ""
    if kind == ProjectType.Kind.ACQUISITION:
        manual("add_property", _("Add the property to the register"),
               _admin("property_add", name=project.name, address_line_1=first_line), _("Add the property"))
        manual("add_title", _("Add the title and its documents"),
               _admin("title_add", **({"title_number": project.site_title_number} if project.site_title_number else {})),
               _("Add the title"))
        out.append(Step("link_property", _("Link the new property to this project (Add a property, above)"),
                        done=bool(links), automatic=True))
    elif kind == ProjectType.Kind.DEVELOPMENT:
        parent = next((link.property for link in links if link.part == ProjectProperty.Part.DEVELOP),
                      links[0].property if links else None)
        params = {"parent": parent.pk} if parent else {}
        manual("add_units", _("Add the new buildings or units to the register"), _admin("property_add", **params),
               _("Add a unit"))
        if can_use(user, "compliance") and parent:
            manual("golden_thread", _("Screen new buildings for the Golden Thread and add their building information"),
                   reverse("compliance:property", args=[parent.pk]), _("Open compliance"))
    elif kind == ProjectType.Kind.DISPOSAL:
        for link in links:
            if link.part == ProjectProperty.Part.DISPOSE:
                out.append(Step(f"dispose_{link.property_id}",
                                _("Record the disposal of %(ref)s %(name)s: completion date and price") % {
                                    "ref": link.property.reference, "name": link.property.name},
                                _admin("property_change", link.property_id), _("Record the disposal"),
                                done=bool(link.property.disposed_on), automatic=True))
        manual("tell_finance", _("Tell finance the sale proceeds and the assets to remove from the asset register"))
    elif kind == ProjectType.Kind.PROGRAMME:
        manual("confirm_complete", _("Confirm the work is complete at every property in the programme"))
    else:
        manual("record_decision", _("Record the decision and start any projects that follow from it"),
               reverse("projects:new"), _("Start a project"))

    if kind in (ProjectType.Kind.ACQUISITION, ProjectType.Kind.DEVELOPMENT) and can_use(user, "valuations"):
        target = links[0].property if links else None
        manual("valuation", _("Classify and value the new asset for the accounts"),
               reverse("valuations:property", args=[target.pk]) if target else "",
               _("Open asset valuation") if target else "")
    manual("final_budget", _("Enter the final actual figures in the budget"))
    return out
