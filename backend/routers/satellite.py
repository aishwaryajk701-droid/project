"""Satellite data discovery + geocoding (map search)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from lib import ext_http
from lib.geo import PolygonError, bbox_from_polygon, validate_polygon
from lib.security import current_user
from models.agrigaurd import DiscoverIn
from services import sentinel_service

router = APIRouter(prefix="/satellite", tags=["satellite"])


@router.get("/status")
async def satellite_status(user: Dict[str, Any] = Depends(current_user)):
    return {"sentinel_hub_configured": sentinel_service.configured(),
            "collections": ["sentinel-1-grd", "sentinel-2-l2a"] if sentinel_service.configured() else [],
            "note": ("When configured, data is described as 'Latest Available Satellite "
                     "Observation' — never 'live'.")}


@router.post("/discover")
async def discover(body: DiscoverIn, user: Dict[str, Any] = Depends(current_user)):
    """Satellite data discovery for a polygon: lists available observations (S1/S2)."""
    coords = body.coordinates
    try:
        validate_polygon(coords)
    except PolygonError as exc:
        raise HTTPException(400, str(exc))
    bbox = bbox_from_polygon(coords)
    if not sentinel_service.configured():
        return {"sentinel_hub_configured": False,
                "observations": [],
                "message": ("Sentinel Hub credentials not configured — satellite observation "
                            "discovery is DATA UNAVAILABLE. Add SENTINEL_HUB_CLIENT_ID/_SECRET to "
                            "backend/.env; soil, terrain, weather and map context still work.")}
    from datetime import date, timedelta
    today = date.today()
    s1 = await sentinel_service.catalog_search(bbox, (today - timedelta(days=30)).isoformat(),
                                               today.isoformat(), "sentinel-1-grd", limit=20)
    s2 = await sentinel_service.catalog_search(bbox, (today - timedelta(days=30)).isoformat(),
                                               today.isoformat(), "sentinel-2-l2a", limit=20,
                                               max_cloud=40)
    def obs(features: Optional[List[Dict]], satellite: str) -> List[Dict[str, Any]]:
        out = []
        for f in (features or [])[:10]:
            p = f.get("properties", {})
            out.append({"satellite": satellite, "id": f.get("id"),
                        "acquired": p.get("datetime"),
                        "cloud_pct": p.get("eo:cloud_cover"),
                        "orbit": p.get("satellite_orbit_state"),
                        "quality": "available"})
        return out
    observations = obs(s1, "Sentinel-1 GRD") + obs(s2, "Sentinel-2 L2A")
    return {"sentinel_hub_configured": True, "observations": observations,
            "latest_available": observations[0]["acquired"] if observations else None,
            "note": "Latest Available Satellite Observation (not live)"}


# --- map search via Nominatim (keyless) ---

@router.get("/geocode")
async def geocode(q: str, user: Dict[str, Any] = Depends(current_user)):
    if not q or len(q.strip()) < 3:
        raise HTTPException(400, "Query too short")
    data = await ext_http.request(
        "GET", "https://nominatim.openstreetmap.org/search", source="geocode",
        params={"q": q.strip(), "format": "json", "limit": 6},
        headers={"User-Agent": "AgriGaurd/1.0 (field mapping)"})
    results = []
    for r in data if isinstance(data, list) else []:
        results.append({"display_name": r.get("display_name"), "lat": float(r.get("lat")),
                        "lng": float(r.get("lon")), "type": r.get("type")})
    return {"results": results, "source": "OpenStreetMap Nominatim"}
