"""Daily flood check: re-analyse every monitored field, alert on new water.

Triggered by the platform cron (.emergent/crons.yml -> /api/cron/daily-flood-check).
Each user gets at most one digest email per run; SMS only when they configured a
number. Alerts always carry the real evidence from the analysis — no estimates.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from lib.db import db
from services import notification_service
from services.analysis_service import create_job, run_job

logger = logging.getLogger("agriguard.daily")

NEW_WATER_DELTA_PCT = 1.0  # pp increase in agricultural flood that counts as "new water"


async def _previous_pct(field_id: str) -> float | None:
    doc = await db.analyses.find_one(
        {"field_id": field_id, "type": "satellite", "demo": {"$ne": True}},
        {"_id": 0, "flood": 1}, sort=[("created_at", -1)])
    if not doc:
        return None
    return (doc.get("flood") or {}).get("agricultural_flood_pct")


async def _analyse_field(user: Dict[str, Any], field: Dict[str, Any]) -> Dict[str, Any] | None:
    coords = (field.get("boundary") or {}).get("coordinates")
    if not coords:
        return None
    job = await create_job(user, coords, field=field)
    await run_job(job["job_id"], coords, user, field, False)
    return await db.analyses.find_one({"field_id": field["id"], "user_id": user["id"]},
                                      {"_id": 0}, sort=[("created_at", -1)])


async def run_daily_flood_check(run_id: str) -> None:
    started = datetime.now(timezone.utc)
    scanned = 0
    alerted = 0
    per_user: Dict[str, List[Dict[str, Any]]] = {}

    try:
        configs = await db.monitoring_configs.find({"enabled": True}).to_list(200)
        for cfg in configs:
            field = await db.fields.find_one({"id": cfg["field_id"], "user_id": cfg["user_id"]},
                                             {"_id": 0})
            user = await db.users.find_one({"id": cfg["user_id"]}, {"_id": 0, "password_hash": 0})
            if not field or not user:
                continue
            prev_pct = await _previous_pct(field["id"])
            try:
                analysis = await _analyse_field(user, field)
            except Exception as exc:
                logger.warning("daily scan failed for field %s: %s", field["id"], exc)
                continue
            if not analysis:
                continue
            scanned += 1
            flood = analysis.get("flood") or {}
            new_pct = flood.get("agricultural_flood_pct")
            severity = flood.get("severity", "none")
            delta = (round(new_pct - prev_pct, 2)
                     if new_pct is not None and prev_pct is not None else None)

            new_water = (new_pct is not None and
                         ((prev_pct is None and new_pct >= NEW_WATER_DELTA_PCT) or
                          (delta is not None and delta >= NEW_WATER_DELTA_PCT)))
            if new_water:
                alerted += 1
                await notification_service.notify_flood(user, field, analysis)
                headline = f"New water detected — {severity}"
                detail = (f"{new_pct}% agricultural flood"
                          + (f" (was {prev_pct}%, +{delta} pp)" if delta is not None else "")
                          + f", {flood.get('affected_ha', 0)} ha affected, "
                            f"confidence {(flood.get('confidence') or {}).get('score', '—')}/100")
            elif new_pct is None:
                headline = "No flood data"
                detail = "Satellite flood metrics unavailable — partial analysis saved"
            else:
                headline = "No new water"
                detail = f"{new_pct}% agricultural flood, unchanged within {NEW_WATER_DELTA_PCT} pp"

            per_user.setdefault(user["id"], []).append(
                {"user": user, "field": field.get("name"), "headline": headline,
                 "detail": detail, "new_water": new_water})

            await db.monitoring_configs.update_one(
                {"id": cfg["id"]},
                {"$set": {"last_run": started.isoformat(),
                          "last_state": "new_water" if new_water else "no_change"}})

        # one digest per user, only when they enabled email alerts
        for uid, items in per_user.items():
            user = items[0]["user"]
            prefs = await db.alert_prefs.find_one({"user_id": uid}, {"_id": 0}) or {}
            if not prefs.get("email_enabled"):
                continue
            try:
                import emailer
                if not emailer.email_configured():
                    continue
                html = emailer.daily_digest_html(name=user.get("name", "there"),
                                                 items=items, scanned=len(items))
                await emailer.send_email(
                    to=prefs.get("alert_email") or user.get("email"),
                    subject=("AgriGaurd daily flood check — new water detected"
                             if any(i["new_water"] for i in items)
                             else "AgriGaurd daily flood check — no new water"),
                    html=html)
            except Exception as exc:
                logger.warning("digest email failed for %s: %s", uid, exc)

        await db.cron_runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "completed", "scanned": scanned, "alerted": alerted,
                      "users_notified": len(per_user),
                      "finished_at": datetime.now(timezone.utc).isoformat()}})
        logger.info("daily flood check %s: scanned=%s alerted=%s", run_id, scanned, alerted)
    except Exception as exc:
        logger.exception("daily flood check crashed")
        await db.cron_runs.update_one({"run_id": run_id},
                                      {"$set": {"status": "failed", "error": str(exc)[:300]}})


async def run_for_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Manual 'run the daily check now' for one user's monitored fields."""
    configs = await db.monitoring_configs.find(
        {"enabled": True, "user_id": user["id"]}).to_list(50)
    results = []
    for cfg in configs:
        field = await db.fields.find_one({"id": cfg["field_id"], "user_id": user["id"]}, {"_id": 0})
        if not field:
            continue
        coords = (field.get("boundary") or {}).get("coordinates")
        if not coords:
            continue
        job = await create_job(user, coords, field=field)
        asyncio.create_task(run_job(job["job_id"], coords, user, field, False))
        results.append({"field_id": field["id"], "field": field.get("name"),
                        "job_id": job["job_id"]})
    return {"queued": len(results), "jobs": results}
