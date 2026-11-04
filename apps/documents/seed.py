# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load the templates supplied with PHAEMA from apps/documents/library. A council's own changes are kept:
supplied templates are only added, never overwritten."""
from pathlib import Path

LIBRARY = Path(__file__).parent / "library"


def parse(path):
    text = path.read_text(encoding="utf-8")
    head, body = text.split("\n---\n", 1)
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    start = (LIBRARY / "_letter_start.txt").read_text(encoding="utf-8").strip()
    body = body.replace("[[letter_start]]", start).strip() + "\n"
    fields = []
    for spec in filter(None, (s.strip() for s in meta.get("fields", "").split(" ; "))):
        parts = [p.strip() for p in spec.split("|")] + ["", "", ""]
        flags = {f.strip() for f in parts[2].split(",")}
        fields.append({"key": parts[0], "label": parts[1], "long": "long" in flags,
                       "optional": "optional" in flags, "help": parts[3]})
    return {
        "code": path.stem.replace("_", "-"), "name": meta["name"], "category": meta.get("category", "general"),
        "source": meta.get("source", "case"), "description": meta.get("description", ""),
        "case_types": [c.strip() for c in meta.get("case_types", "").split(",") if c.strip()],
        "prescribed_form": meta.get("prescribed_form", ""), "letterhead": meta.get("letterhead", "yes") != "no",
        "extra_fields": fields, "body": body,
    }


def supplied():
    return [parse(p) for p in sorted(LIBRARY.glob("*.txt")) if not p.name.startswith("_")]


def ensure_templates():
    from .models import DocumentTemplate

    for i, spec in enumerate(supplied()):
        code = spec.pop("code")
        DocumentTemplate.objects.get_or_create(code=code, defaults={**spec, "shipped": True, "order": i * 10})
