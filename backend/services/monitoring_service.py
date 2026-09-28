"""Smart monitoring: per-field schedules (daily / every 3 days / weekly), scan-now, and a
lightweight in-process scheduler that checks due configs every 5 minutes."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from lib.db import db
from lib.security import new_id
from services import notification_service
from services.analysis_service import run_job

logger = logging.getLogger("agriguard.monitoring")

INTERVALS = {"daily": 1, "every_3_days": 3, "weekly": 7}
SIGNIFICANT_DELTA_PCT = 3.0  # alert when ag flood % moves this much between runs


async def upsert_config(user: Dict[str, Any], field_id: str, frequency: str, enabled: bool) -> Dict[str, Any]:
    if frequency not in INTERVALS:
        raise ValueError("frequency must be daily, every_3_days or weekly")
    next_run = (datetime.now(timezone.utc) + timedelta(days=INTERVALS[frequency])).isoformat()
    doc = {"id": new_id(), "user_id": user["id"], "field_id": field_id, "frequency": frequency,
           "enabled": enabled, "next_run": next_run, "last_run": None, "last_state": None,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.monitoring_configs.update_one(
        {"user_id": user["id"], "field_id": field_id}, {"$set": doc}, upsert=True)
    return doc


async def run_scan(user: Dict[str, Any], field: Dict[str, Any], coordinates) -> Dict[str, Any]:
    """Prepare one monitoring cycle for a field (caller schedules run_job)."""
    from services.analysis_service import create_job
    job = await create_job(user, coordinates, field=field)
    prev = await db.analyses.find_one(
        {"field_id": field["id"], "type": "satellite", "demo": {"$ne": True}},
        sort=[("created_at", -1)])
    if prev:
        prev_flood = ((prev.get("flood") or {}).get("agricultural_flood_pct")) or 0.0
        await notification_service.notify(
            user["id"], kind="monitoring", severity="info",
            title=f"Scan started — {field.get('name', 'field')}",
            body=f"Monitoring scan queued. Previous agricultural flood: {prev_flood}%.",
            field_id=field["id"], analysis_id=None)
    return job


async def check_and_alert_change(user: Dict[str, Any], field: Dict[str, Any],
                                 analysis: Dict[str, Any]) -> None:
    """Compare the new analysis with the previous one and alert on significant change."""
    if analysis.get("demo"):
        return
    prev = None
    async for doc in db.analyses.find(
            {"field_id": field["id"], "type": "satellite", "demo": {"$ne": True},
             "id": {"$ne": analysis["id"]}}).sort("created_at", -1).limit(1):
        prev = doc
    new_pct = ((analysis.get("flood") or {}).get("agricultural_flood_pct")) or 0.0
    if prev is None:
        return
    prev_pct = ((prev.get("flood") or {}).get("agricultural_flood_pct")) or 0.0
    delta = round(new_pct - prev_pct, 2)
    if abs(delta) >= SIGNIFICANT_DELTA_PCT:
        direction = "increased" if delta > 0 else "decreased"
        sev = "high" if delta > 8 and new_pct > 10 else ("moderate" if delta > 0 else "info")
        await notification_service.notify(
            user["id"], kind="flood" if delta > 0 else "monitoring", severity=sev,
            title=f"Significant flood change — {field.get('name', 'field')}",
            body=(f"Agricultural flood {direction} from {prev_pct}% to {new_pct}% "
                  f"(Δ {delta} pp). Evidence: SAR new-water {((analysis.get('flood') or {}).get('new_water_pct'))}%."),
            field_id=field["id"], analysis_id=analysis.get("id"))


async def scheduler_loop() -> None:
    """Every 5 minutes: find due, enabled configs and kick off scans."""
    while True:
        try:
            now = datetime.now(timezone.utc).isoformat()
            due = await db.monitoring_configs.find(
                {"enabled": True, "next_run": {"$lte": now}}).to_list(50)
            for cfg in due:
                field = await db.fields.find_one({"id": cfg["field_id"], "user_id": cfg["user_id"]})
                user = await db.users.find_one({"id": cfg["user_id"]}, {"_id": 0, "password_hash": 0})
                if not field or not user:
                    continue
                coords = (field.get("boundary") or {}).get("coordinates")
                if not coords:
                    continue
                await run_scan(user, field, coords)
                await db.monitoring_configs.update_one(
                    {"id": cfg["id"]},
                    {"$set": {"last_run": now,
                              "next_run": (datetime.now(timezone.utc)
                                           + timedelta(days=INTERVALS.get(cfg["frequency"], 7))).isoformat()}})
                await notification_service.audit(user["id"], "monitoring_scan",
                                                 {"field_id": field["id"]})
        except Exception as exc:
            logger.warning("monitoring loop error: %s", exc)
        await asyncio.sleep(300)
