"""Field insights: sowing calendar and Village Compare benchmark."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from lib.db import db
from lib.security import current_user
from services import village_service
from services.sowing_service import build_calendar

router = APIRouter(prefix="/fields", tags=["insights"])


async def _owned_field(field_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db.fields.find_one({"id": field_id, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Field not found")
    return doc


@router.get("/{field_id}/sowing-calendar")
async def sowing_calendar(field_id: str, user: Dict[str, Any] = Depends(current_user)):
    field = await _owned_field(field_id, user)
    analysis = await db.analyses.find_one(
        {"field_id": field_id, "user_id": user["id"], "type": "satellite"},
        {"_id": 0}, sort=[("created_at", -1)])
    if not analysis:
        raise HTTPException(404, "No analysis available for this field yet — run an analysis first")
    return build_calendar(analysis, field)


@router.get("/{field_id}/village-compare")
async def village_compare(field_id: str, radius_km: float = 25.0,
                          user: Dict[str, Any] = Depends(current_user)):
    field = await _owned_field(field_id, user)
    radius = max(1.0, min(radius_km, 200.0))
    return await village_service.compare_field(field, user["id"], radius_km=radius)
