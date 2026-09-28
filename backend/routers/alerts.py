"""Alert preferences + notification center."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from lib.db import db
from lib.security import current_user
from models.agrigaurd import AlertPrefsIn
from services.notification_service import _SEVERITY_RANK, audit

router = APIRouter(tags=["alerts"])


@router.get("/alerts/preferences")
async def get_alert_prefs(user: Dict[str, Any] = Depends(current_user)):
    doc = await db.alert_prefs.find_one({"user_id": user["id"]}, {"_id": 0})
    if not doc:
        return {"user_id": user["id"], "email_enabled": False, "alert_email": user.get("email"),
                "sms_enabled": False, "alert_phone": "", "min_severity": "moderate"}
    return doc


@router.put("/alerts/preferences")
async def set_alert_prefs(body: AlertPrefsIn, user: Dict[str, Any] = Depends(current_user)):
    sev = (body.min_severity or "moderate").lower()
    if sev not in _SEVERITY_RANK:
        sev = "moderate"
    doc = {"user_id": user["id"], "email_enabled": body.email_enabled,
           "alert_email": body.alert_email or user.get("email"),
           "sms_enabled": body.sms_enabled, "alert_phone": (body.alert_phone or "").strip(),
           "min_severity": sev,
           "updated_at": __import__("datetime").datetime.now(
               __import__("datetime").timezone.utc).isoformat()}
    await db.alert_prefs.update_one({"user_id": user["id"]}, {"$set": doc}, upsert=True)
    return doc


@router.post("/alerts/test")
async def send_test_alert(user: Dict[str, Any] = Depends(current_user)):
    import emailer
    import sms as sms_mod
    prefs = await db.alert_prefs.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    sent: Dict[str, Any] = {}
    if emailer.email_configured():
        to = prefs.get("alert_email") or user.get("email")
        eid = await emailer.send_email(to=to, subject="AgriGaurd test flood alert",
                                       html=emailer.flood_alert_html(
                                           name=user.get("name", "there"), field_name="Sample Field",
                                           severity="high", flood_pct=18.4, affected_ha=12.3, area_ha=67.0))
        sent["email"] = {"to": to, "ok": bool(eid)}
    phone = prefs.get("alert_phone")
    if sms_mod.sms_configured() and phone:
        sid = await sms_mod.send_sms(to=phone, body=sms_mod.flood_alert_sms(
            field_name="Sample Field", severity="high", flood_pct=18.4, affected_ha=12.3))
        sent["sms"] = {"to": phone, "ok": bool(sid)}
    if not sent:
        raise HTTPException(400, "No alert channel configured (email/SMS not set up on server).")
    return {"sent": sent}


@router.get("/notifications")
async def notifications(view: str = "all", limit: int = 100,
                        user: Dict[str, Any] = Depends(current_user)):
    q: Dict[str, Any] = {"user_id": user["id"]}
    if view == "unread":
        q["read"] = False
    elif view == "critical":
        q["severity"] = {"$in": ["high", "critical"]}
    elif view == "information":
        q["severity"] = {"$in": ["info", "low", "moderate"]}
    docs: List[Dict[str, Any]] = []
    cur = db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 300))
    return [d async for d in cur]


@router.post("/notifications/{nid}/read")
async def mark_read(nid: str, user: Dict[str, Any] = Depends(current_user)):
    r = await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    if r.matched_count == 0:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(user: Dict[str, Any] = Depends(current_user)):
    await db.notifications.update_many({"user_id": user["id"], "read": False},
                                       {"$set": {"read": True}})
    return {"ok": True}
