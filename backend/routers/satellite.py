"""Satellite data discovery + geocoding (map search)."""

import asyncio
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


@router.post("/search")
async def multi_satellite_search(body: DiscoverIn, days: int = 60,
                                 user: Dict[str, Any] = Depends(current_user)):
    """Multi-satellite scene search over the farm polygon (AOI) and a date range.

    Each source keeps ONE defined role; unavailable sources report DATA UNAVAILABLE
    with the exact reason instead of being filled in with estimates.
    """
    coords = body.coordinates
    try:
        validate_polygon(coords)
    except PolygonError as exc:
        raise HTTPException(400, str(exc))
    bbox = bbox_from_polygon(coords)
    window = max(7, min(days, 365))

    from lib.ext_http import safe
    from services import landsat_service, nasa_service, nisar_service
    from services.multisat_service import DISCLAIMER, ROLES

    ls, nisar = await asyncio.gather(
        safe("landsat", lambda: landsat_service.search_scenes(bbox, days=window),
             "USGS Landsat Collection 2"),
        nisar_service.search_scenes(bbox, days=window))

    sources: List[Dict[str, Any]] = []
    if sentinel_service.configured():
        from datetime import date, timedelta
        today = date.today()
        start = (today - timedelta(days=window)).isoformat()
        s1 = await sentinel_service.catalog_search(bbox, start, today.isoformat(),
                                                   "sentinel-1-grd", limit=20)
        s2 = await sentinel_service.catalog_search(bbox, start, today.isoformat(),
                                                   "sentinel-2-l2a", limit=20, max_cloud=60)
        for feats, name in ((s1, "Sentinel-1 GRD"), (s2, "Sentinel-2 L2A")):
            scenes = [{"scene_id": f.get("id"), "acquired": f.get("properties", {}).get("datetime"),
                       "cloud_pct": f.get("properties", {}).get("eo:cloud_cover")}
                      for f in (feats or [])[:10]]
            sources.append({"satellite": name, "status": "AVAILABLE" if scenes else "NO SCENES",
                            "role": ROLES["sentinel1" if "1" in name else "sentinel2"],
                            "scene_count": len(scenes), "scenes": scenes,
                            "resolution": "approximately 10 m", "source": "Copernicus / Sentinel Hub"})
    else:
        for key, name in (("sentinel1", "Sentinel-1 GRD"), ("sentinel2", "Sentinel-2 L2A")):
            sources.append({"satellite": name, "status": "NOT CONFIGURED", "role": ROLES[key],
                            "scene_count": 0, "scenes": [],
                            "message": ("Sentinel Hub credentials not configured — add "
                                        "SENTINEL_HUB_CLIENT_ID/_SECRET to backend/.env")})

    if ls["status"] == "OK":
        d = ls["data"]
        sources.append({"satellite": "Landsat 8/9 (Collection 2 L2)", "status": "AVAILABLE",
                        "role": ROLES["landsat"], "scene_count": d["scene_count"],
                        "scenes": d["scenes"], "resolution": "30 m", "source": d["source"],
                        "note": d["note"]})
    else:
        sources.append({"satellite": "Landsat 8/9 (Collection 2 L2)", "status": "DATA UNAVAILABLE",
                        "role": ROLES["landsat"], "scene_count": 0, "scenes": [],
                        "message": ls.get("error") or "USGS STAC search unavailable"})

    sources.append({"satellite": "NISAR (L-band SAR)", "status": nisar["status"],
                    "role": nisar["role"], "scene_count": 0, "scenes": [],
                    "message": nisar["message"], "source": nisar["source"]})

    nasa_products = [{"satellite": f"NASA — {p['product']}", "status": p["status"],
                      "role": ROLES["nasa"], "scene_count": 0, "scenes": [],
                      "message": p["detail"]} for p in nasa_service.unavailable_products()]
    sources.append({"satellite": "NASA POWER (MERRA-2 / GEOS)", "status": "AVAILABLE",
                    "role": ROLES["nasa"], "scene_count": 0, "scenes": [],
                    "source": "NASA POWER", "resolution": "approximately 0.5 deg",
                    "note": "Daily rainfall and temperature — keyless, used as an independent cross-check"})
    sources += nasa_products

    return {"bbox": bbox, "window_days": window,
            "available_count": sum(1 for s in sources if s["status"] == "AVAILABLE"),
            "sources": sources, "disclaimer": DISCLAIMER}


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
