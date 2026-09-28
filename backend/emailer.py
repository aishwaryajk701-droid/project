"""Email alerts through Emergent's managed email integration.

No Resend account or API key is needed — the platform owns the provider account.
Templates live here (server-side only); callers pass data, never markup.
"""

import ipaddress
import logging
import os
import re
from html import escape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agriguard.email")

# Emergent managed email proxy. CONSTANT — never read from os.environ.
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "AgriGaurd")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")


def email_configured() -> bool:
    return bool(EMAIL_KEY)


# --------------------------------------------------------------------------- gate
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set = set()
        self.urls: List[str] = []
        self.anchors: List[tuple] = []
        self._href: Optional[str] = None
        self._text: List[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        parsed = urlparse(low)
        if not _host_ok(parsed.hostname or "") or parsed.username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


# --------------------------------------------------------------------------- send
async def send_email(*, to: str, subject: str, html: str,
                     reply_to: str | None = None) -> str | None:
    """Internal helper. `html` always comes from a template below, never request input."""
    if not email_configured():
        return None
    _assert_safe_email(subject, html)
    payload: Dict[str, Any] = {"to": [to], "subject": subject, "html": html,
                               "from_name": EMAIL_FROM_NAME}
    if reply_to or EMAIL_REPLY_TO:
        payload["contact_email"] = reply_to or EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                     headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as exc:
        logger.error("email send failed: %s %s", exc.response.status_code, exc.response.text[:300])
        return None
    except Exception as exc:
        logger.error("email send error: %s", exc)
        return None


# ----------------------------------------------------------------------- templates
_WRAP = ('<table role="presentation" width="100%" style="background:#0B130E;padding:24px">'
         '<tr><td align="center"><table role="presentation" width="600" '
         'style="background:#101B14;border:1px solid #1E3A2B;border-radius:12px;'
         'font-family:Arial,Helvetica,sans-serif;color:#E6EFE9">'
         '<tr><td style="padding:24px">{body}'
         '<p style="font-size:11px;color:#8FA398;margin-top:24px;line-height:1.5">'
         'Sent by {brand}. Remote-sensing based estimate &middot; analytical confidence is not a '
         'validated probability &middot; field verification recommended. '
         'We never ask for your password or payment details by email.'
         '</p></td></tr></table></td></tr></table>')


def _row(label: str, value: str) -> str:
    return (f'<tr><td style="padding:4px 12px 4px 0;font-size:13px;color:#8FA398">{escape(label)}</td>'
            f'<td style="padding:4px 0;font-size:13px;font-weight:bold">{escape(value)}</td></tr>')


def flood_alert_html(*, name: str, field_name: str, severity: str, flood_pct: Any,
                     affected_ha: Any, area_ha: Any) -> str:
    body = (
        f'<h2 style="margin:0 0 8px;font-size:20px">Flood alert — {escape(field_name)}</h2>'
        f'<p style="font-size:14px;line-height:1.6">Hi {escape(name)}, AgriGaurd detected a '
        f'<strong>{escape(severity.upper())}</strong> flood condition on this field in the latest '
        f'available satellite observation.</p>'
        f'<table role="presentation">'
        f'{_row("Agricultural flood", f"{flood_pct}%")}'
        f'{_row("Affected area", f"{affected_ha} ha of {area_ha} ha")}'
        f'{_row("Severity", str(severity))}'
        f'</table>'
        f'<p style="font-size:13px;line-height:1.6;margin-top:16px">Open AgriGaurd and check the '
        f'field page for the evidence behind this result, the water breakdown and the updated crop '
        f'recommendation.</p>')
    return _WRAP.format(body=body, brand=escape(EMAIL_FROM_NAME))


def daily_digest_html(*, name: str, items: List[Dict[str, Any]], scanned: int) -> str:
    rows = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;font-size:13px">{escape(str(i["field"]))}</td>'
        f'<td style="padding:6px 12px 6px 0;font-size:13px;font-weight:bold">{escape(str(i["headline"]))}</td>'
        f'<td style="padding:6px 0;font-size:12px;color:#8FA398">{escape(str(i["detail"]))}</td></tr>'
        for i in items)
    body = (
        f'<h2 style="margin:0 0 8px;font-size:20px">Daily flood check</h2>'
        f'<p style="font-size:14px;line-height:1.6">Hi {escape(name)}, AgriGaurd scanned '
        f'{scanned} monitored field(s) today.</p>'
        f'<table role="presentation" width="100%">{rows}</table>')
    return _WRAP.format(body=body, brand=escape(EMAIL_FROM_NAME))
