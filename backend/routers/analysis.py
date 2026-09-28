"""Analysis jobs + history + comparison + exports (CSV/JSON)."""

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from lib.db import db
from lib.geo import PolygonError, validate_polygon
from lib.security import current_user, new_id
from models.agrigaurd import AnalyzeIn
from services.analysis_service import create_job, run_job
from services.notification_service import audit

router = APIRouter(tags=["analysis"])


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc.pop("_id", None)
    return doc


@router.post("/analyze")
async def analyze(body: AnalyzeIn, background: BackgroundTasks,
                  user: Dict[str, Any] = Depends(current_user)):
    """Run the full pipeline on a polygon. Optionally saves it as a new field."""
    # Always reject an unusable boundary up front, whether or not it is being saved.
    try:
        validate_polygon(body.coordinates)
    except PolygonError as exc:
        raise HTTPException(400, str(exc))

    field = None
    if body.field_id:
        field = await db.fields.find_one({"id": body.field_id, "user_id": user["id"]})
        if not field:
            raise HTTPException(404, "Field not found")
    elif body.save_as_field:
        from lib.geo import polygon_area_ha, validate_polygon, bbox_from_polygon, polygon_centroid
        try:
            validate_polygon(body.coordinates)
        except PolygonError as exc:
            raise HTTPException(400, str(exc))
        area_ha = polygon_area_ha(body.coordinates)
        lng, lat = polygon_centroid(body.coordinates)
        field = {"id": new_id(), "user_id": user["id"],
                 "name": body.field_name or f"Field {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
                 "state": None, "district": None, "village": None,
                 "latitude": lat, "longitude": lng,
                 "boundary": {"name": body.field_name or "Field", "coordinates": body.coordinates},
                 "bbox": bbox_from_polygon(body.coordinates), "area_ha": round(area_ha, 3),
                 "created_at": datetime.now(timezone.utc).isoformat(), "last_analysis": None,
                 "flood_status": "UNKNOWN", "flood_pct": None, "flood_confidence": None,
                 "land_suitability": None, "recommended_crop": None,
                 "monitoring": {"enabled": False, "frequency": "weekly"}}
        await db.fields.insert_one(field.copy())
        await audit(user["id"], "field_created", {"field_id": field["id"]})

    job = await create_job(user, body.coordinates, field=field, demo=body.demo)
    background.add_task(run_job, job["job_id"], body.coordinates, user, field, body.demo)
    await audit(user["id"], "analysis_started", {"job_id": job["job_id"], "demo": body.demo})
    return {"job_id": job["job_id"], "state": job["state"], "field_id": (field or {}).get("id")}


@router.get("/analysis/jobs/{job_id}")
async def job_status(job_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await db.analysis_jobs.find_one({"job_id": job_id, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Job not found")
    return doc


@router.get("/analyses")
async def list_analyses(user: Dict[str, Any] = Depends(current_user),
                        type: Optional[str] = None, field_id: Optional[str] = None,
                        min_flood: Optional[float] = None,
                        date_from: Optional[str] = None, date_to: Optional[str] = None,
                        limit: int = 50):
    q: Dict[str, Any] = {"user_id": user["id"]}
    if type:
        q["type"] = type
    if field_id:
        q["field_id"] = field_id
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("created_at", {})["$lte"] = date_to + ("T23:59:59Z" if len(date_to) == 10 else "")
    proj = {"_id": 0, "images": 0, "items": 0, "original_image_b64": 0, "processed_image_b64": 0,
            "osm_context": 0}
    docs: List[Dict[str, Any]] = []
    if min_flood is not None:
        q["flood.agricultural_flood_pct"] = {"$gte": min_flood}
    cur = db.analyses.find(q, proj).sort("created_at", -1).limit(min(limit, 300))
    return [ _clean(d) async for d in cur ]


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await db.analyses.find_one({"id": analysis_id, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")
    return doc


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    r = await db.analyses.delete_one({"id": analysis_id, "user_id": user["id"]})
    return {"deleted": r.deleted_count}


@router.get("/analyses/{analysis_id}/compare/{other_id}")
async def compare_analyses(analysis_id: str, other_id: str,
                           user: Dict[str, Any] = Depends(current_user)):
    async def load(aid: str) -> Dict[str, Any]:
        d = await db.analyses.find_one({"id": aid, "user_id": user["id"]}, {"_id": 0})
        if not d:
            raise HTTPException(404, f"Analysis {aid} not found")
        return d
    a, b = await load(analysis_id), await load(other_id)

    def metric(d: Dict[str, Any]) -> Dict[str, Any]:
        flood = d.get("flood") or {}
        return {
            "agricultural_flood_pct": flood.get("agricultural_flood_pct"),
            "affected_ha": flood.get("agricultural_flood_ha"),
            "total_water_pct": flood.get("total_water_pct"),
            "confidence": (flood.get("confidence") or {}).get("score"),
            "ndvi": (d.get("ndvi") or {}).get("mean") if d.get("ndvi") else None,
            "ndmi": (d.get("ndmi") or {}).get("mean") if d.get("ndmi") else None,
            "land_suitability": (d.get("land_suitability") or {}).get("score"),
            "crop_score": (((d.get("crops") or {}).get("recommendations") or [{}])[0].get("score")),
            "crop": (((d.get("crops") or {}).get("recommendations") or [{}])[0].get("crop")),
        }
    ma, mb = metric(a), metric(b)
    deltas = {}
    for k in ma:
        va, vb = ma[k], mb[k]
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            deltas[k] = {"absolute": round(vb - va, 3),
                         "pct": round(((vb - va) / va * 100.0), 1) if va else None,
                         "direction": "increase" if vb > va else "decrease" if vb < va else "same"}
        else:
            deltas[k] = {"absolute": None, "pct": None,
                         "direction": "changed" if va != vb else "same"}
    return {"base": {"id": a["id"], "date": a.get("created_at"), "metrics": ma},
            "other": {"id": b["id"], "date": b.get("created_at"), "metrics": mb},
            "deltas": deltas}


@router.get("/analyses/{analysis_id}/export/json")
async def export_json(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await get_analysis(analysis_id, user)
    for k in ("images", "items", "original_image_b64", "processed_image_b64"):
        doc.pop(k, None)
    return doc


@router.get("/analyses/{analysis_id}/export/csv")
async def export_csv(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await get_analysis(analysis_id, user)
    flood = doc.get("flood") or {}
    conf = flood.get("confidence") or {}
    ls = doc.get("land_suitability") or {}
    dq = doc.get("data_quality") or {}
    rows = [
        ("metric", "value"),
        ("analysis_id", doc.get("id")),
        ("created_at", doc.get("created_at")),
        ("demo", doc.get("demo", False)),
        ("field_id", doc.get("field_id")),
        ("area_ha", doc.get("area_ha")),
        ("flood_status", flood.get("status")),
        ("flood_severity", flood.get("severity")),
        ("total_water_pct", flood.get("total_water_pct")),
        ("new_water_pct", flood.get("new_water_pct")),
        ("agricultural_flood_pct", flood.get("agricultural_flood_pct")),
        ("agricultural_flood_ha", flood.get("agricultural_flood_ha")),
        ("confidence_score", conf.get("score")),
        ("land_suitability_score", ls.get("score")),
        ("data_quality_score", dq.get("score")),
        ("ndvi_mean", (doc.get("ndvi") or {}).get("mean") if doc.get("ndvi") else None),
        ("ndmi_mean", (doc.get("ndmi") or {}).get("mean") if doc.get("ndmi") else None),
    ]
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=agrigaurd-{analysis_id[:8]}.csv"})


@router.get("/export/csv")
async def export_all_csv(user: Dict[str, Any] = Depends(current_user)):
    q = {"user_id": user["id"]}
    proj = {"_id": 0, "images": 0, "items": 0, "original_image_b64": 0, "processed_image_b64": 0,
            "osm_context": 0, "boundary": 0, "bbox": 0}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "type", "created_at", "area_ha", "severity",
                     "agricultural_flood_pct", "confidence", "land_suitability", "demo"])
    async for d in db.analyses.find(q, proj).sort("created_at", -1).limit(1000):
        flood = d.get("flood") or {}
        writer.writerow([d.get("id"), d.get("type"), d.get("created_at"), d.get("area_ha"),
                         flood.get("severity"), flood.get("agricultural_flood_pct"),
                         (flood.get("confidence") or {}).get("score"),
                         (d.get("land_suitability") or {}).get("score"), d.get("demo", False)])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=agrigaurd-analyses.csv"})
