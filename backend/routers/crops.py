"""Crop knowledge base + ad-hoc recommendation."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from lib.db import db
from lib.geo import PolygonError, bbox_from_polygon, polygon_centroid, validate_polygon
from lib.security import current_user
from models.agrigaurd import RecommendIn
from services import crop_engine, soil_service, terrain_service, weather_service
from services.crop_engine import CROPS

router = APIRouter(prefix="/crops", tags=["crops"])


@router.get("")
async def list_crops(user: Dict[str, Any] = Depends(current_user)):
    return {"crops": CROPS, "count": len(CROPS),
            "note": "Requirement ranges from ICAR/FAO agronomic references."}


@router.post("/recommend")
async def recommend(body: RecommendIn, user: Dict[str, Any] = Depends(current_user)):
    """Ad-hoc crop recommendation for a polygon (uses real keyless sources)."""
    try:
        validate_polygon(body.coordinates)
    except PolygonError as exc:
        raise HTTPException(400, str(exc))
    bbox = bbox_from_polygon(body.coordinates)
    lng, lat = polygon_centroid(body.coordinates)

    async def _soil():
        return await soil_service.fetch_soil(lat, lng)

    async def _terrain():
        return await terrain_service.fetch_terrain(bbox)

    async def _weather():
        rr = await weather_service.recent_rainfall(lat, lng, 30)
        return rr

    from lib.ext_http import safe

    soil, terrain, rain = await __import__("asyncio").gather(
        safe("soil", _soil), safe("terrain", _terrain), safe("weather", _weather))
    rec = crop_engine.recommend_crops(
        soil=soil.get("data"), terrain=terrain.get("data"), flood_severity=None,
        ag_flood_pct=None, ndmi=None, rain7=(rain.get("data") or {}).get("last_7_days_mm")
        if rain.get("data") else None,
        month=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).month,
        state=body.state)
    rec["soil_status"] = soil["status"]
    rec["terrain_status"] = terrain["status"]
    rec["weather_status"] = rain["status"]
    rec["note"] = ("Recommendation computed without a flood analysis — run a full analysis for "
                   "flood-condition-aware rankings.")
    return rec
