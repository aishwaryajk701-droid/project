"""My Fields — CRUD, analysis trigger, history, monitoring config."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from lib.db import db
from lib.geo import PolygonError, bbox_from_polygon, polygon_area_ha, polygon_centroid, validate_polygon
from lib.security import current_user, new_id
from models.agrigaurd import FieldCreate, FieldUpdate, MonitoringIn
from services import monitoring_service
from services.analysis_service import create_job, run_job
from services.notification_service import audit

router = APIRouter(prefix="/fields", tags=["fields"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc


async def _owned_field(field_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db.fields.find_one({"id": field_id, "user_id": user["id"]})
    if not doc:
        raise HTTPException(404, "Field not found")
    return doc


@router.get("")
async def list_fields(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    docs = await db.fields.find({"user_id": user["id"]}, {"_id": 0}) \
                          .sort("created_at", -1).to_list(500)
    return docs


@router.post("")
async def create_field(body: FieldCreate, user: Dict[str, Any] = Depends(current_user)):
    try:
        validate_polygon(body.coordinates)
    except PolygonError as exc:
        raise HTTPException(400, str(exc))
    bbox = bbox_from_polygon(body.coordinates)
    area_ha = polygon_area_ha(body.coordinates)
    if body.latitude and body.longitude:
        lat, lng = body.latitude, body.longitude
    else:
        lng, lat = polygon_centroid(body.coordinates)
    doc = {
        "id": new_id(), "user_id": user["id"], "name": body.name,
        "state": body.state, "district": body.district, "village": body.village,
        "latitude": lat, "longitude": lng,
        "boundary": {"name": body.name, "coordinates": body.coordinates},
        "bbox": bbox, "area_ha": round(area_ha, 3),
        "created_at": _now(), "last_analysis": None,
        "flood_status": "UNKNOWN", "flood_pct": None, "flood_confidence": None,
        "land_suitability": None, "recommended_crop": None,
        "monitoring": {"enabled": False, "frequency": "weekly"},
    }
    await db.fields.insert_one(doc.copy())
    await audit(user["id"], "field_created", {"field_id": doc["id"], "area_ha": doc["area_ha"]})
    return _clean(doc)


@router.get("/{field_id}")
async def get_field(field_id: str, user: Dict[str, Any] = Depends(current_user)):
    return _clean(await _owned_field(field_id, user))


@router.patch("/{field_id}")
async def update_field(field_id: str, body: FieldUpdate,
                       user: Dict[str, Any] = Depends(current_user)):
    await _owned_field(field_id, user)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        updates["updated_at"] = _now()
        await db.fields.update_one({"id": field_id, "user_id": user["id"]}, {"$set": updates})
    return _clean(await _owned_field(field_id, user))


@router.delete("/{field_id}")
async def delete_field(field_id: str, user: Dict[str, Any] = Depends(current_user)):
    await _owned_field(field_id, user)
    await db.fields.delete_one({"id": field_id, "user_id": user["id"]})
    await db.monitoring_configs.update_one({"field_id": field_id}, {"$set": {"enabled": False}})
    await audit(user["id"], "field_deleted", {"field_id": field_id})
    return {"deleted": True}


@router.post("/{field_id}/analyze")
async def analyze_field(field_id: str, background: BackgroundTasks,
                        demo: bool = False, user: Dict[str, Any] = Depends(current_user)):
    field = await _owned_field(field_id, user)
    coords = (field.get("boundary") or {}).get("coordinates") or []
    job = await create_job(user, coords, field=field, demo=demo)
    background.add_task(run_job, job["job_id"], coords, user, field, demo)
    await audit(user["id"], "analysis_started", {"field_id": field_id, "demo": demo})
    return {"job_id": job["job_id"], "state": job["state"]}


@router.get("/{field_id}/history")
async def field_history(field_id: str, limit: int = 100,
                        user: Dict[str, Any] = Depends(current_user)):
    await _owned_field(field_id, user)
    docs = await db.analyses.find(
        {"field_id": field_id, "user_id": user["id"]},
        {"_id": 0, "images": 0, "items": 0, "original_image_b64": 0, "processed_image_b64": 0,
         "osm_context": 0}) \
        .sort("created_at", -1).limit(min(limit, 300)).to_list(limit)
    return docs


@router.get("/{field_id}/monitoring")
async def get_monitoring(field_id: str, user: Dict[str, Any] = Depends(current_user)):
    await _owned_field(field_id, user)
    doc = await db.monitoring_configs.find_one({"user_id": user["id"], "field_id": field_id},
                                               {"_id": 0}) or {"enabled": False, "frequency": "weekly"}
    return doc


@router.put("/{field_id}/monitoring")
async def set_monitoring(field_id: str, body: MonitoringIn,
                         user: Dict[str, Any] = Depends(current_user)):
    await _owned_field(field_id, user)
    try:
        doc = await monitoring_service.upsert_config(user, field_id, body.frequency, body.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await db.fields.update_one({"id": field_id, "user_id": user["id"]},
                               {"$set": {"monitoring": {"enabled": body.enabled,
                                                        "frequency": body.frequency}}})
    return doc


@router.post("/{field_id}/monitoring/scan")
async def scan_now(field_id: str, background: BackgroundTasks,
                   user: Dict[str, Any] = Depends(current_user)):
    field = await _owned_field(field_id, user)
    coords = (field.get("boundary") or {}).get("coordinates") or []
    try:
        validate_polygon(coords)
    except PolygonError as exc:
        raise HTTPException(400, str(exc))
    job = await monitoring_service.run_scan(user, field, coords)
    background.add_task(run_job, job["job_id"], coords, user, field, False)
    return {"job_id": job["job_id"], "state": job["state"]}
