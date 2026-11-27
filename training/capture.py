# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture screenshots for the e-learning and the website tour from a running PHAEMA with the demonstration data.

    DATABASE_URL=... python training/capture.py http://localhost:8000 shots.json
    DATABASE_URL=... python training/capture.py http://localhost:8000 course   (every step in course.py)

shots.json is a list of {"name", "user", "url", "selector", "dest"} and an optional "click" (a part to click first,
such as a details summary to open): dest is "training" (saved as
static/training/img/<name>.jpg, with the highlight box in training/boxes.json) or "website" (website/img/<name>.jpg).
The script signs each user in by making a Django session for them (so it needs the same DATABASE_URL and settings as
the server), opens the page at 1280 by 800, scrolls the selected part into view and records where it is.
Needs Playwright (pip install playwright) and Chrome or Chromium.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "phaema.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

WIDTH, HEIGHT = 1280, 800


def _record(kind, key):
    """The database number of a demonstration record named by its reference, so the addresses in course.py work
    on any copy of the demonstration data. {kind:key} in an address is replaced by the number (or, for leasefile,
    by the file's whole address)."""
    from django.contrib.auth import get_user_model

    from apps.cases.models import Case, CaseType, SiteVisit
    from apps.leases.models import Lease, LeaseDocument, LeaseEvent
    from apps.maintenance.models import Job
    from apps.projects.models import Project
    from apps.properties.models import Property
    from apps.reports.models import Report
    from apps.servicecharges.models import Schedule, ScheduleYear
    from apps.space.models import Occupier
    from apps.strategy.models import HealthCheck, Objective
    from apps.valuations.models import Valuation

    def numbered(model, ref):  # CAS-2026-0033, PRJ-2026-001, JOB-2026-0014
        _prefix, year, number = ref.split("-")[:3]
        return model.objects.get(year=int(year), number=int(number)).pk

    if kind == "property":
        return Property.objects.get(reference=key).pk
    if kind == "lease":
        return Lease.objects.get(reference=key).pk
    if kind == "event":  # DL-0501/review: the lease's next open event of that type
        lease, event_type = key.split("/")
        return (LeaseEvent.objects.filter(lease__reference=lease, event_type=event_type)
                .order_by("status", "due_date").first().pk)
    if kind == "leasefile":  # DL-0001/lease.pdf
        lease, filename = key.split("/")
        return LeaseDocument.objects.filter(lease__reference=lease, original_filename=filename).first().file.url
    if kind == "case":
        return numbered(Case, key)
    if kind == "visit":
        return SiteVisit.objects.filter(case_id=numbered(Case, key)).order_by("visited_on").first().pk
    if kind == "project":
        return numbered(Project, key)
    if kind == "job":
        return numbered(Job, key)
    if kind == "objective":
        return Objective.objects.filter(number=int(key)).order_by("-pk").first().pk
    if kind == "health":
        return HealthCheck.objects.get(year=int(key)).pk
    if kind == "schedule":
        return Schedule.objects.get(name=key).pk
    if kind == "scyear":  # schedule name/the year it starts
        name, year = key.split("/")
        return ScheduleYear.objects.get(schedule__name=name, start__year=int(year)).pk
    if kind == "occupier":
        return Occupier.objects.get(cost_centre=key).pk
    if kind == "valuation":  # the property's latest
        return Valuation.objects.filter(property__reference=key).order_by("-pk").first().pk
    if kind == "report":
        return Report.objects.filter(name=key).order_by("pk").first().pk
    if kind == "user":
        return get_user_model().objects.get(username=key).pk
    if kind == "casetype":
        return CaseType.objects.get(code=key).pk
    if kind == "run":  # latest: the newest demand run
        from apps.ledger.models import DemandRun

        return DemandRun.objects.order_by("-pk").first().pk
    if kind == "repair":  # a lease reference: its newest repair report from the tenant portal
        from apps.maintenance.models import RepairReport

        return RepairReport.objects.filter(lease__reference=key).order_by("-pk").first().pk
    if kind == "request":  # a lease reference: its newest request made in the tenant portal
        return Case.objects.filter(lease__reference=key, how_received="portal").order_by("-pk").first().pk
    raise ValueError(f"Unknown record kind {kind}")


def resolve(url):
    import re

    return re.sub(r"\{(\w+):([^}]+)\}", lambda m: str(_record(m.group(1), m.group(2))), url)


# Steps that need a state the script cannot set up (text typed into the PDF viewer's Find, a scan with its text
# recognised), so their pictures are kept as they are when every step is re-captured.
KEEP = {"leases-5", "find-4", "find-5"}

# Steps whose highlighted part is inside something closed, which is clicked open first.
CLICKS = {"rents-6": "#ifrs16 summary"}


def course_shots():
    sys.path.insert(0, str(ROOT / "training"))
    import course

    modules = [course.START] + [m for c in course.COURSES for m in c["modules"]]
    shots = []
    for m in modules:
        for i, (user, url, selector, _title, _text) in enumerate(m["steps"], 1):
            name = f"{m['id']}-{i}"
            if name in KEEP:
                continue
            shot = {"name": name, "user": user, "url": resolve(url), "selector": selector, "dest": "training"}
            if name in CLICKS:
                shot["click"] = CLICKS[name]
            shots.append(shot)
    return list({s["name"]: s for s in shots}.values())  # a module shared by two courses once


def session_for(username):
    user = get_user_model().objects.get(username=username)
    store = SessionStore()
    store[SESSION_KEY] = str(user.pk)
    store[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    store.create()
    return store.session_key


def main(base, spec_path):
    shots = course_shots() if spec_path == "course" else json.loads(Path(spec_path).read_text())
    problems = []
    boxes_path = ROOT / "training" / "boxes.json"
    boxes = json.loads(boxes_path.read_text())
    sessions = {user: session_for(user) for user in {shot["user"] for shot in shots}}  # before the browser starts
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get("CAPTURE_CHANNEL", "chrome"))
        for shot in shots:
            user = shot["user"]
            context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            context.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": sessions[user], "url": base}])
            page = context.new_page()
            response = page.goto(base + shot["url"], wait_until="networkidle")
            if response is None or response.status >= 400:
                problems.append(f"{shot['name']}: {shot['url']} answered {response.status if response else 'nothing'}")
                context.close()
                continue
            if shot.get("selector") and page.locator(shot["selector"]).count() == 0:
                problems.append(f"{shot['name']}: {shot['selector']} not found on {shot['url']}")
                context.close()
                continue
            if shot.get("click"):  # open a closed panel first, such as a details summary
                page.locator(shot["click"]).first.click()
                page.evaluate("document.activeElement && document.activeElement.blur()")
                page.wait_for_timeout(200)
            box = None
            if shot.get("selector"):
                element = page.locator(shot["selector"]).first
                element.scroll_into_view_if_needed()
                page.evaluate("window.scrollBy(0, -80)")  # a little context above the highlighted part
                page.wait_for_timeout(300)
                found = element.bounding_box()
                if found:
                    x, y = max(found["x"], 0), max(found["y"], 0)
                    w = min(found["width"], WIDTH - x)
                    h = min(found["height"], HEIGHT - y)
                    box = [round(x / WIDTH, 4), round(y / HEIGHT, 4), round(w / WIDTH, 4), round(h / HEIGHT, 4)]
            if shot["dest"] == "training":
                out = ROOT / "static" / "training" / "img" / f"{shot['name']}.jpg"
                if box:
                    boxes[shot["name"]] = box
            else:
                out = ROOT / "website" / "img" / f"{shot['name']}.jpg"
            page.screenshot(path=str(out), type="jpeg", quality=82)
            print(out.relative_to(ROOT), box or "")
            context.close()
        browser.close()
    boxes_path.write_text(json.dumps(boxes))
    for problem in problems:  # the old picture is kept for these
        print("NOT CAPTURED", problem)


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"), sys.argv[2])
