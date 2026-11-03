# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read a saved email (.eml from any mail program, .msg from Outlook) so it can be filed on a case."""
import re
from dataclasses import dataclass, field
from datetime import date
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime


@dataclass
class ParsedEmail:
    sender: str = ""
    recipients: str = ""
    subject: str = ""
    sent: date = None
    text: str = ""
    attachments: list = field(default_factory=list)  # [(filename, bytes)]


def _plain(html):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def parse_eml(data):
    msg = BytesParser(policy=policy.default).parsebytes(data)
    out = ParsedEmail(sender=str(msg.get("From", "")), recipients=str(msg.get("To", "")),
                      subject=str(msg.get("Subject", "")))
    try:
        out.sent = parsedate_to_datetime(msg["Date"]).date() if msg["Date"] else None
    except (TypeError, ValueError):
        out.sent = None
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is not None:
        content = body.get_content()
        out.text = content if body.get_content_type() == "text/plain" else _plain(content)
    for part in msg.iter_attachments():
        name = part.get_filename()
        payload = part.get_payload(decode=True)
        if name and payload:
            out.attachments.append((name, payload))
    return out


def parse_msg(data):
    import io

    import extract_msg

    msg = extract_msg.openMsg(io.BytesIO(data))
    try:
        out = ParsedEmail(sender=msg.sender or "", recipients=msg.to or "", subject=msg.subject or "")
        sent = msg.date
        out.sent = sent.date() if hasattr(sent, "date") else None
        out.text = msg.body or ""
        for att in msg.attachments:
            name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None)
            payload = getattr(att, "data", None)
            if name and isinstance(payload, bytes):
                out.attachments.append((name, payload))
        return out
    finally:
        msg.close()


def parse(filename, data):
    """A ParsedEmail for a .eml or .msg file, or None for anything else (or an unreadable file)."""
    ext = filename.rsplit(".", 1)[-1].lower()
    try:
        if ext == "eml":
            return parse_eml(data)
        if ext == "msg":
            return parse_msg(data)
    except Exception:  # a damaged email is still filed, just without the details read from it
        return None
    return None
