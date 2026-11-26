# SPDX-License-Identifier: AGPL-3.0-or-later
"""The annual asset management health check.

A short self-assessment a head of estates completes once a year. The questions are PHAEMA's own, grouped under the
headings used by the RICS guidance on strategic public sector property asset management (practice information, 3rd
edition), which is credited as the basis. No RICS text is reproduced. Administrators can change the list.
"""
from datetime import date

from apps.projects.models import financial_year_label, financial_year_of

CREDIT = ("The questions are PHAEMA's own, grouped under the headings of the RICS guidance on strategic public "
          "sector property asset management, which this check is organised around. They are a prompt, not a "
          "standard: change them to suit the council.")

# (heading, question, what a good answer looks like)
STARTING_QUESTIONS = [
    ("strategy", "Does the council have a current, approved asset management strategy that serves its corporate "
     "plan?", "Adopted by members within its period, with each objective tied to a corporate aim."),
    ("strategy", "Does every property have a recorded purpose and asset strategy?",
     "Holding purpose and asset strategy recorded for each property, from retain to dispose."),
    ("strategy", "Is every property reviewed on a rolling programme (Asset Challenge) within the strategy period?",
     "Strategy review dates set, few overdue, outcomes recorded and decided by the right body."),
    ("planning", "Is there an asset management plan of actions with owners, dates and costs, refreshed at least "
     "once a year?", "An action plan under each objective, kept up to date and reported."),
    ("planning", "Do services state their future property needs, and does the plan reflect them?",
     "Service asset plans or similar, collected each year and used to shape the plan."),
    ("finance", "Is the full cost of holding each building known and used in decisions?",
     "Running costs, maintenance and capital costs recorded by building and used in option appraisals."),
    ("finance", "Are capital receipts and investment needs forecast for at least five years?",
     "Disposals, acquisitions and projects in a dated pipeline with values, linked to the capital programme."),
    ("finance", "Is the return on property held for income measured against a target?",
     "Income, voids and arrears tracked against targets for the investment portfolio."),
    ("demand", "Is how intensively buildings are used measured?",
     "Capacity, headcount or public use figures for operational buildings, refreshed regularly."),
    ("demand", "Are chances to share buildings with partners actively pursued?",
     "Shared occupation with other public bodies recorded, for example through One Public Estate."),
    ("demand", "Are lease breaks and expiries used to ask whether the council still needs the space?",
     "Each break or expiry where the council is tenant triggers a review well before the notice date."),
    ("operations", "Is maintenance planned from recent condition surveys, with a costed backlog?",
     "Condition surveys under five years old for most buildings; backlog known by priority."),
    ("operations", "Are statutory compliance checks up to date and recorded?",
     "Fire, asbestos, water, gas and electrical checks in date, with remedial actions tracked."),
    ("operations", "Are rent reviews, renewals and arrears managed to timetable?",
     "Few missed review dates; arrears followed up promptly; lease events handled before deadlines."),
    ("governance", "Is there a cross-council property board, or equivalent, that owns the strategy?",
     "A board with senior members from services and finance, meeting regularly, with minutes."),
    ("governance", "Is one senior officer accountable for the estate as a corporate resource?",
     "A corporate landlord approach: services occupy buildings but do not own them."),
    ("governance", "Are property decisions recorded with who made them, when and the minute reference?",
     "Decisions traceable to a delegated officer, committee or cabinet decision."),
    ("client", "Does the council have the skills to specify, buy and manage outside property advice and "
     "contracts?", "Qualified staff who set briefs, check advice and manage contracts and consultants."),
    ("client", "Are property staff and their skills enough for the work in the plan?",
     "Workload and skills reviewed against the plan, with gaps filled by training or recruitment."),
    ("policies", "Are there current policies for acquisitions, disposals, community asset transfer and discounted "
     "lettings?", "Policies adopted, published and applied, with exceptions recorded."),
    ("policies", "Is social value considered and recorded in property decisions?",
     "Social value, including below-market lettings, weighed and recorded in decisions."),
    ("policies", "Are there targets for energy, carbon and net zero across the estate, with progress measured?",
     "Baseline and yearly figures, targets set, and progress reported."),
    ("data", "Is the property register complete and trusted, with a named owner for each kind of data?",
     "Few gaps in key fields; data owners named; regular checks of completeness."),
    ("data", "Does property information inform decisions, rather than simply being stored?",
     "Reports from the register used in board papers, option appraisals and budget setting."),
    ("data", "Can the council produce key estate figures quickly when asked?",
     "Count, area, value, running cost and income by portfolio produced in hours, not weeks."),
    ("review", "Is progress on the strategy reported to members at least once a year?",
     "A yearly report on objectives, actions and key figures, with the minute reference."),
    ("review", "Were last year's health check findings acted on?",
     "Gaps from last year carried into the action plan and closed or explained."),
]

ORDER = {"yes": 3, "partly": 2, "no": 1}
SCORE_LABELS = {"better": "Better", "worse": "Worse", "same": "Same", "new": "New"}


def ensure_questions():
    """Load the starting questions if the list is empty. Safe to run again."""
    from .models import HealthQuestion

    if HealthQuestion.objects.exists():
        return
    for n, (heading, text, guidance) in enumerate(STARTING_QUESTIONS, start=1):
        HealthQuestion.objects.create(heading=heading, text=text, guidance=guidance, order=n * 10)


def current_year(today=None):
    return financial_year_of(today or date.today())


def start(lead, year=None, today=None):
    """Start the year's check with every question in use, unanswered. Returns the existing check if there is one."""
    from .models import HealthAnswer, HealthCheck, HealthQuestion

    year = year or current_year(today)
    check, created = HealthCheck.objects.get_or_create(year=year, defaults={"lead": lead})
    if created:
        ensure_questions()
        # The check's creation is logged; its blank question rows are not, one by one. Answers given are.
        HealthAnswer.objects.bulk_create([
            HealthAnswer(health_check=check, question=q, heading=q.heading, wording=q.text, guidance=q.guidance,
                         order=q.order) for q in HealthQuestion.objects.filter(active=True)])
    return check


def _match(answer, previous):
    """The answer to the same question in an earlier check: by question, or failing that by wording."""
    if previous is None:
        return None
    for p in previous:
        if answer.question_id and p.question_id == answer.question_id:
            return p
    for p in previous:
        if p.wording == answer.wording:
            return p
    return None


def change(now, before):
    """"better", "worse", "same" or "new" between this year's answer and last year's."""
    if before is None or not before.answer:
        return "new"
    a, b = ORDER.get(now.answer), ORDER.get(before.answer)
    if a is None or b is None:
        return "same" if now.answer == before.answer else "new"
    return "better" if a > b else "worse" if a < b else "same"


def sections(check):
    """[(heading label, [(answer, last year's answer, change)])] in question order, headings in their usual order."""
    from .models import HealthQuestion

    prev = check.previous()
    earlier = list(prev.answers.all()) if prev else None
    grouped = {}
    for a in check.answers.select_related("answered_by", "action").prefetch_related("comments__author"):
        before = _match(a, earlier)
        grouped.setdefault(a.heading, []).append((a, before, change(a, before) if prev and a.answer else ""))
    return [(label, grouped[value]) for value, label in HealthQuestion.Heading.choices if value in grouped]


def counts(check):
    found = {"yes": 0, "partly": 0, "no": 0, "na": 0, "": 0}
    for value in check.answers.values_list("answer", flat=True):
        found[value] = found.get(value, 0) + 1
    found["open"] = found[""]
    return found


def build_report(check, user=None, today=None):
    """The check's report in the document library's markup, for the page and the Word download."""
    from apps.properties.report import _date, _head, _name, _para, _row

    today = today or date.today()
    prev = check.previous()
    c = counts(check)
    out = [f"# {check}", "",
           f"Financial year {financial_year_label(check.year)}. Lead: {_name(check.lead) or 'not set'}. "
           + (f"Finished {_date(check.finished_on)}." if check.finished_on else f"In progress at {_date(today)}."),
           "", "# Summary", "",
           f"Yes: {c['yes']}. Partly: {c['partly']}. No: {c['no']}. Not applicable: {c['na']}."
           + (f" Not yet answered: {c['']}." if c[""] else ""), ""]
    if prev:
        moves = {"better": 0, "worse": 0, "same": 0}
        for _label, rows in sections(check):
            for _a, _b, ch in rows:
                if ch in moves:
                    moves[ch] += 1
        out += [f"Compared with {financial_year_label(prev.year)}: {moves['better']} better, {moves['worse']} "
                f"worse, {moves['same']} the same.", ""]
    if check.summary:
        out += _para(check.summary)
    gaps = [a for _l, rows in sections(check) for a, _b, _c in rows if a.is_gap]
    if gaps:
        out += ["# Gaps and improvement actions", "", _head("Question", "Answer", "Improvement action")]
        for a in gaps:
            action = a.action.label if a.action_id else "None yet"
            out.append(_row(a.wording, a.get_answer_display(), action))
        out.append("")
    for label, rows in sections(check):
        out += [f"# {label}", ""]
        heads = ["Question", "Answer"] + ([f"{financial_year_label(prev.year)}", "Change"] if prev else [])
        out.append(_head(*heads))
        for a, before, ch in rows:
            cells = [a.wording, a.get_answer_display() or "Not answered"]
            if prev:
                cells += [before.get_answer_display() if before and before.answer else "", SCORE_LABELS.get(ch, "")]
            out.append(_row(*cells))
        out.append("")
        for a, _b, _c in rows:
            if a.notes or a.evidence:
                out += [f"**{a.wording}**", ""]
                if a.notes:
                    out += _para(a.notes)
                if a.evidence:
                    out += ["Evidence: " + "; ".join(a.evidence_lines()), ""]
    out += ["# About this check", "", CREDIT, ""]
    return "\n".join(out)
