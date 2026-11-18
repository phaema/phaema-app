# SPDX-License-Identifier: AGPL-3.0-or-later
"""How each action and objective is going, and the board report built from them."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Action, EstateStrategy, Objective

SOON_DAYS = 30
RANK = {"red": 3, "amber": 2, "green": 1}


@dataclass
class ActionState:
    action: Action
    rag: str  # red, amber, green, done or dropped
    reason: str
    label: str
    url: str = ""
    hidden: bool = False  # a confidential project this person cannot see
    flags: list = field(default_factory=list)  # exceptions: late, over budget, high risk

    @property
    def is_open(self):
        return self.rag not in ("done", "dropped")


def action_state(action, user=None, today=None):
    today = today or date.today()
    a = action
    if a.project_id:
        from apps.projects import budget, rules

        p = a.project
        hidden = user is not None and not rules.can_see(user, p)
        label = "A confidential project" if hidden else f"{p.display_reference} {p.name}"
        if not p.is_open:
            done = p.status == p.Status.CLOSED
            return ActionState(a, "done" if done else "dropped", p.get_status_display(), label,
                               "" if hidden else p.get_absolute_url(), hidden)
        colour, reason = p.rag(today)
        rag = {"red": "red", "yellow": "amber"}.get(colour, "green")
        flags = []
        if colour == "red":
            flags.append(str(reason))
        variance = budget.summary(p)["cost"].variance
        if variance > 0:
            flags.append(f"£{variance:,.0f} over budget")
            rag = "red" if rag == "red" else "amber"
        high = [r for r in p.risks.filter(status="open") if r.score >= 15]
        if high:
            flags.append(f"{len(high)} high risk{'s' if len(high) > 1 else ''}")
            rag = "red" if rag == "red" else "amber"
        return ActionState(a, rag, str(reason), label, "" if hidden else p.get_absolute_url(), hidden, flags)
    if a.case_id:
        c = a.case
        label = f"{c.display_reference} {c.title}"
        if not c.is_open:
            return ActionState(a, "done", c.get_status_display(), label, c.get_absolute_url())
        colour, reason = c.rag(today)
        rag = {"red": "red", "orange": "amber"}.get(colour, "green")
        return ActionState(a, rag, str(reason), label, c.get_absolute_url(),
                           flags=[str(reason)] if rag == "red" else [])
    if a.status == Action.Status.DONE:
        return ActionState(a, "done", "Done", a.label)
    if a.status == Action.Status.DROPPED:
        return ActionState(a, "dropped", "Dropped", a.label)
    if a.target_date and a.target_date < today:
        return ActionState(a, "red", "Past target date", a.label, flags=["Past target date"])
    if a.target_date and a.target_date <= today + timedelta(days=SOON_DAYS):
        return ActionState(a, "amber", "Due within a month", a.label)
    return ActionState(a, "green", a.get_status_display(), a.label)


@dataclass
class ObjectiveState:
    objective: Objective
    actions: list
    suggested: str  # red, amber, green, done or ""
    reason: str

    @property
    def shown(self):
        """The status the owner reported, or else the one PHAEMA suggests."""
        return self.objective.reported_status or self.suggested

    @property
    def differs(self):
        return bool(self.objective.reported_status and self.suggested
                    and self.objective.reported_status != self.suggested)

    @property
    def late(self):
        return [s for s in self.actions if s.rag == "red"]

    @property
    def exceptions(self):
        return [s for s in self.actions if s.flags]

    @property
    def done_count(self):
        return sum(1 for s in self.actions if s.rag == "done")


def objective_state(objective, user=None, today=None):
    today = today or date.today()
    states = [action_state(a, user, today) for a in objective.actions.select_related(
        "project", "project__project_type", "case", "case__case_type", "owner")]
    live = [s for s in states if s.is_open]
    if not states:
        return ObjectiveState(objective, states, "", "No actions yet")
    if not live:
        return ObjectiveState(objective, states, "done", "Every action is done")
    worst = max(live, key=lambda s: RANK.get(s.rag, 0))
    suggested, reason = worst.rag, f"{worst.label}: {worst.reason}"
    if objective.target_date and objective.target_date < today:
        suggested, reason = "red", "The objective's target date has passed"
    return ObjectiveState(objective, states, suggested, reason)


RAG_TAG = {"red": "govuk-tag--red", "amber": "govuk-tag--yellow", "green": "govuk-tag--green",
           "done": "govuk-tag--blue", "dropped": "govuk-tag--grey"}
RAG_WORDS = {"red": "Off track", "amber": "At risk", "green": "On track", "done": "Achieved", "dropped": "Dropped"}


def board(strategy, user=None, today=None):
    """Everything the board report shows, for one strategy."""
    from apps.cases.models import Case
    from apps.properties import strategy as property_strategy

    today = today or date.today()
    objectives = [objective_state(o, user, today) for o in strategy.objectives.select_related("owner")]
    counts = {k: sum(1 for o in objectives if o.shown == k) for k in ("green", "amber", "red", "done")}
    counts["none"] = sum(1 for o in objectives if not o.shown)
    year_ago = today - timedelta(days=365)
    challenges = Case.objects.filter(case_type__asset_challenge=True).select_related("property", "proposed_strategy")
    return {
        "strategy": strategy, "today": today, "objectives": objectives, "counts": counts,
        "exceptions": [(o, s) for o in objectives for s in o.exceptions],
        "challenges_open": list(challenges.exclude(status="closed").order_by("received_on")),
        "challenges_decided": list(challenges.filter(decision_on__gte=year_ago,
                                                     decision__in=("approved", "conditions"))
                                   .prefetch_related("strategies__strategy").order_by("-decision_on")),
        "overview": property_strategy.overview(today),
    }
