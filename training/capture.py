# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture screenshots for the e-learning and the website tour from a running PHAEMA with the demonstration data.

    DATABASE_URL=... python training/capture.py http://localhost:8000 shots.json

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


def session_for(username):
    user = get_user_model().objects.get(username=username)
    store = SessionStore()
    store[SESSION_KEY] = str(user.pk)
    store[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    store.create()
    return store.session_key


def main(base, spec_path):
    shots = json.loads(Path(spec_path).read_text())
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
            page.goto(base + shot["url"], wait_until="networkidle")
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


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"), sys.argv[2])
