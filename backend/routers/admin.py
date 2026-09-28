"""Admin panel analytics (role ADMIN only)."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from lib.db import db
from lib.security import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
async def overview(user: Dict[str, Any] = Depends(require_role("ADMIN"))):
    counts = {
        "users": await db.users.count_documents({}),
        "fields": await db.fields.count_documents({}),
        "analyses": await db.analyses.count_documents({}),
        "flood_events": await db.analyses.count_documents({"flood.status": "DETECTED"}),
        "monitoring_jobs": await db.monitoring_configs.count_documents({"enabled": True}),
        "notifications": await db.notifications.count_documents({}),
    }

    async def by_month(col: str, field: str = "created_at") -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        cur = db[col].aggregate([
            {"$group": {"_id": {"$substr": [f"${field}", 0, 7]}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}])
        async for d in cur:
            out.append({"month": d["_id"], "count": d["count"]})
        return out

    users_over_time = await by_month("users")
    analyses_over_time = await by_month("analyses")

    severity_rows: List[Dict[str, Any]] = []
    cur = db.analyses.aggregate([
        {"$match": {"type": "satellite"}},
        {"$group": {"_id": "$flood.severity", "count": {"$sum": 1}}}
    ])
    async for d in cur:
        severity_rows.append({"severity": d["_id"] or "unavailable", "count": d["count"]})

    crop_rows: List[Dict[str, Any]] = []
    cur = db.analyses.aggregate([
        {"$unwind": "$crops.recommendations"},
        {"$sort": {"crops.recommendations.score": -1}},
        {"$group": {"_id": "$crops.recommendations.crop", "count": {"$sum": 1},
                    "avg_score": {"$avg": "$crops.recommendations.score"}}},
        {"$sort": {"count": -1}}, {"$limit": 8}])
    async for d in cur:
        crop_rows.append({"crop": d["_id"], "count": d["count"],
                          "avg_score": round(d.get("avg_score") or 0, 1)})

    recent_errors: List[Dict[str, Any]] = []
    cur = db.audit_log.find({"event": {"$in": ["analysis_failed"]}},
                            {"_id": 0}).sort("created_at", -1).limit(10)
    recent_errors = [d async for d in cur]

    return {"counts": counts, "users_over_time": users_over_time,
            "analyses_over_time": analyses_over_time, "flood_severity": severity_rows,
            "crop_recommendations": crop_rows, "recent_errors": recent_errors,
            "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/users")
async def users(user: Dict[str, Any] = Depends(require_role("ADMIN"))):
    docs: List[Dict[str, Any]] = []
    cur = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(200)
    async for d in cur:
        d["field_count"] = await db.fields.count_documents({"user_id": d["id"]})
        d["analysis_count"] = await db.analyses.count_documents({"user_id": d["id"]})
        docs.append(d)
    return docs


@router.get("/audit")
async def audit_log(limit: int = 100, user: Dict[str, Any] = Depends(require_role("ADMIN"))):
    cur = db.audit_log.find({}, {"_id": 0}).sort("created_at", -1).limit(min(limit, 300))
    return [d async for d in cur]
