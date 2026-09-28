"""In-app notifications + email/SMS fan-out. Secrets stay in backend/.env; absent channels
degrade to in-app only."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from lib.db import db
from lib.security import new_id

logger = logging.getLogger("agriguard.notify")

_SEVERITY_RANK = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}


async def notify(user_id: str, *, kind: str, severity: str, title: str, body: str,
                 field_id: str | None = None, analysis_id: str | None = None,
                 evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
    doc = {
        "id": new_id(), "user_id": user_id, "kind": kind,  # flood|system|monitoring|report
        "severity": severity, "title": title, "body": body,
        "field_id": field_id, "analysis_id": analysis_id,
        "evidence": evidence or {}, "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one(doc.copy())
    return doc


async def notify_flood(user: Dict[str, Any], field: Dict[str, Any] | None,
                       analysis: Dict[str, Any]) -> List[str]:
    """Create the in-app notification and attempt email/SMS per stored preferences."""
    flood = analysis.get("flood") or {}
    severity = flood.get("severity", "none")
    if _SEVERITY_RANK.get(severity, 0) < _SEVERITY_RANK["low"]:
        return ["in_app"]
    field_name = (field or {}).get("name") or (analysis.get("boundary") or {}).get("name") or "Your field"
    body = (f"{flood.get('agricultural_flood_pct', flood.get('flood_percentage', 0))}% agricultural flood • "
            f"{flood.get('affected_ha', 0)} ha affected • confidence {flood.get('confidence', {}).get('score', '—')}/100")
    await notify(user["id"], kind="flood", severity=severity,
                 title=f"Flood alert — {field_name}", body=body,
                 field_id=(field or {}).get("id"), analysis_id=analysis.get("id"),
                 evidence=(flood.get("evidence") or {}))

    sent: List[str] = ["in_app"]
    prefs = await db.alert_prefs.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    threshold = _SEVERITY_RANK.get(prefs.get("min_severity", "moderate"), 2)
    if _SEVERITY_RANK.get(severity, 0) < threshold:
        return sent

    try:
        import emailer
        if prefs.get("email_enabled") and emailer.email_configured():
            to = prefs.get("alert_email") or user.get("email")
            html = emailer.flood_alert_html(name=user.get("name", "there"), field_name=field_name,
                                            severity=severity,
                                            flood_pct=flood.get("agricultural_flood_pct",
                                                                flood.get("flood_percentage", 0)),
                                            affected_ha=flood.get("affected_ha", 0),
                                            area_ha=analysis.get("area_ha", 0))
            if await emailer.send_email(to=to, subject=f"AgriGaurd {severity.upper()} flood alert — {field_name}", html=html):
                sent.append("email")
    except Exception as exc:
        logger.warning("email alert failed: %s", exc)
    try:
        import sms
        if prefs.get("sms_enabled") and sms.sms_configured() and prefs.get("alert_phone"):
            if await sms.send_sms(to=prefs["alert_phone"],
                                  body=sms.flood_alert_sms(field_name=field_name, severity=severity,
                                                           flood_pct=flood.get("agricultural_flood_pct", 0),
                                                           affected_ha=flood.get("affected_ha", 0))):
                sent.append("sms")
    except Exception as exc:
        logger.warning("sms alert failed: %s", exc)
    return sent


async def audit(user_id: str | None, event: str, detail: Dict[str, Any] | None = None) -> None:
    """Append-only audit trail (never stores passwords/secrets)."""
    try:
        await db.audit_log.insert_one({
            "id": new_id(), "user_id": user_id, "event": event,
            "detail": detail or {}, "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("audit write failed: %s", exc)
