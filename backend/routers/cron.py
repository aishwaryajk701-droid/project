"""Platform cron endpoints. Auth is a bearer secret from backend/.env."""

import hmac
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from lib.db import db
from services import daily_alert_service

logger = logging.getLogger("agriguard.cron")

router = APIRouter(prefix="/cron", tags=["cron"])


def _authorize(authorization: Optional[str]) -> None:
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not secret or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")
    token = authorization.split(" ", 1)[1]
    if not hmac.compare_digest(token, secret):
        raise HTTPException(401, "Unauthorized")


@router.post("/daily-flood-check")
async def daily_flood_check(request: Request, background: BackgroundTasks,
                            authorization: Optional[str] = Header(default=None),
                            x_webhook_id: Optional[str] = Header(default=None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _authorize(authorization)
    try:
        envelope: Dict[str, Any] = await request.json()
    except Exception:
        envelope = {}
    run_id = x_webhook_id or envelope.get("run_id") or "unknown"

    existing = await db.cron_runs.find_one({"run_id": run_id})
    if existing:
        return {"status": "duplicate", "run_id": run_id}
    await db.cron_runs.insert_one({"run_id": run_id, "job": "daily-flood-check",
                                   "status": "accepted"})
    background.add_task(daily_alert_service.run_daily_flood_check, run_id)
    return {"status": "accepted", "run_id": run_id}
