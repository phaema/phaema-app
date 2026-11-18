# SPDX-License-Identifier: AGPL-3.0-or-later
"""A demonstration site visit: a finished visit for the alterations case at DM-E01-U04, with one difference from
the property record still to decide. Invented, like all demonstration data."""
from datetime import date, timedelta

from django.utils import timezone

from . import visit
from .models import Case, SiteVisit

ANSWERS = {
    "Signed in and made yourself known to the occupier": ("checked", ""),
    "Site hazards as recorded": ("yes", ""),
    "Occupied as recorded": ("yes", ""),
    "Use as recorded and permitted": ("yes", "Light industrial and storage, as permitted."),
    "Anyone else in occupation, or parts shared or sublet": ("no", ""),
    "What is there now": ("Steel portal frame unit: open-plan warehouse with a two-storey office block at the "
                          "front. One roller shutter loading door at the rear.", "No description on the record yet."),
    "What is proposed matches the application": ("yes", ""),
    "Work already started or done": ("no", ""),
    "Effect on structure, roof or services": ("Mezzanine to stand on its own steel frame, not on the portal frame. "
                                              "New loading door needs a steel opening in the side cladding and a "
                                              "power supply.", "Ask for the structural engineer's calculations."),
    "Effect on neighbours, common parts or other tenants": ("None seen: the side elevation faces the service "
                                                            "yard.", ""),
    "Other consents likely to be needed": ("Planning permission may be needed for the new opening.", ""),
    "Photographs taken": ("checked", ""),
}


def load(today=None):
    today = today or date.today()
    case = (Case.objects.filter(property__reference="DM-E01-U04", case_type__code="alterations")
            .select_related("owner").first())
    if case is None or case.owner is None or case.visits.exists():
        return None
    sv = visit.start_visit(case, case.owner, today=today - timedelta(days=6))
    sv.time, sv.weather = "10:00 to 11:00", "Dry, overcast"
    sv.people_met = "The tenant's operations manager"
    sv.follow_up = "Ask the tenant for the structural engineer's calculations and fire escape plan for the mezzanine."
    now = timezone.now()
    for a in sv.answers.all():
        a.value, a.note = ANSWERS.get(a.label, ("", ""))
        a.answered_at = now if a.value else None
        a.save()
    sv.status, sv.finished_on = SiteVisit.Status.FINISHED, today - timedelta(days=6)
    sv.save()
    return sv
