# SPDX-License-Identifier: AGPL-3.0-or-later
"""The board report: progress on the estate strategy, as a page and a Word file.

Written in the document library's simple markup (apps/documents/render.py), like the property report.
"""
from datetime import date

from apps.properties.report import _cell, _date, _head, _name, _para, _row, _table

from . import progress


def _rag(code):
    return progress.RAG_WORDS.get(code, "Not reported")


def build(strategy, user=None, today=None):
    today = today or date.today()
    b = progress.board(strategy, user, today)
    out = [f"# Estate strategy progress: {strategy.title}", "",
           f"Prepared {_date(today)}" + (f" by {_name(user)}" if user else "") + ".", ""]
    facts = [("Strategy", strategy.title), ("Period", f"{_date(strategy.starts_on)} to {_date(strategy.ends_on)}"),
             ("Status", strategy.get_status_display()),
             ("Approved", ", ".join(x for x in (strategy.approved_by, _date(strategy.approved_on),
                                                 strategy.minute_reference) if x))]
    out += _table([(k, v) for k, v in facts if v]) + [""]

    n = 1
    c = b["counts"]
    out += [f"# {n}. Summary", "",
            f"{len(b['objectives'])} objectives: {c['green']} on track, {c['amber']} at risk, {c['red']} off track, "
            f"{c['done']} achieved" + (f", {c['none']} not yet reported" if c["none"] else "") + ".", ""]
    ov = b["overview"]
    out += [f"Strategy reviews overdue: {ov['overdue']}; due in the next 90 days: {ov['due_soon']}. "
            f"Asset Challenges in progress: {len(b['challenges_open'])}; decided in the last year: "
            f"{len(b['challenges_decided'])}.", ""]

    n += 1
    out += [f"# {n}. Objectives", "", _head("Objective", "Owner", "Target", "Status", "Actions done")]
    for o in b["objectives"]:
        ob = o.objective
        out.append(_row(str(ob), _name(ob.owner), _date(ob.target_date), _rag(o.shown),
                        f"{o.done_count} of {len(o.actions)}"))
    out.append("")
    for o in b["objectives"]:
        ob = o.objective
        out += [f"## {ob}", ""]
        details = [("Corporate aim", ob.corporate_aim), ("Expected outcomes", ob.outcomes),
                   ("How success is measured", ob.measures), ("Financial effect", ob.financial_effect),
                   ("Risks and opportunities", ob.risks), ("Owner", _name(ob.owner)),
                   ("Target date", _date(ob.target_date)),
                   ("Status", _rag(o.shown) + (f" (PHAEMA suggests {_rag(o.suggested).lower()}: {o.reason})"
                                               if o.differs else ""))]
        out += _table([(k, v) for k, v in details if _cell(v)]) + [""]
        if ob.progress_note:
            out += _para(ob.progress_note)
        if o.actions:
            out += [_head("Action", "Owner", "Target", "Status")]
            for s in o.actions:
                a = s.action
                owner = _name(a.owner) or (_name(a.project.lead) if a.project_id and not s.hidden else "")
                target = _date(a.target_date)
                out.append(_row(s.label, owner, target, f"{_rag(s.rag)}: {s.reason}" if s.is_open else _rag(s.rag)))
            out.append("")
        else:
            out += ["No actions yet.", ""]

    n += 1
    out += [f"# {n}. Exceptions", ""]
    if b["exceptions"]:
        out += [_head("Objective", "Action", "Why")]
        out += [_row(str(o.objective), s.label, "; ".join(s.flags)) for o, s in b["exceptions"]]
        out.append("")
    else:
        out += ["Nothing is late, over budget or carrying a high risk.", ""]

    n += 1
    out += [f"# {n}. Asset Challenges", ""]
    if b["challenges_decided"]:
        out += ["Decided in the last year:", "", _head("Property", "Asset strategy", "Decided", "By")]
        for case in b["challenges_decided"]:
            decision = case.strategies.all()[:1]
            name = decision[0].strategy.name if decision else ""
            prop = f"{case.property.reference} {case.property.name}" if case.property_id else case.title
            out.append(_row(prop, name, _date(case.decision_on),
                            ", ".join(x for x in (case.decided_by, case.minute_reference) if x)))
        out.append("")
    if b["challenges_open"]:
        out += ["In progress:", "", _head("Property", "Stage", "Proposed")]
        for case in b["challenges_open"]:
            prop = f"{case.property.reference} {case.property.name}" if case.property_id else case.title
            out.append(_row(prop, case.get_stage_display(),
                            case.proposed_strategy.name if case.proposed_strategy_id else ""))
        out.append("")
    if not (b["challenges_decided"] or b["challenges_open"]):
        out += ["None in the last year.", ""]

    n += 1
    out += [f"# {n}. The estate", "", _head("Asset strategy", "Decided for", "Including parts")]
    out += [_row(s["option"].name, s["own"], s["total"]) for s in ov["strategies"]]
    out += [_row("Not yet decided", "", ov["without_strategy"]), ""]
    if ov["graded"]:
        out += [_head("Suitability", "Properties")] + [_row(label, count) for _v, label, count in ov["grades"]]
        out.append("")
    return "\n".join(out)
