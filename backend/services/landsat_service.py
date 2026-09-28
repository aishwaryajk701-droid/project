"""Landsat 8/9 — real, keyless scene discovery via the USGS Landsat STAC API.

Search only (no pixel download): USGS serves Collection-2 Level-2 metadata without
credentials, which gives genuine independent optical evidence — acquisition dates,
cloud cover, platform, WRS path/row and the scene id. Pixel-level NDVI/NDWI from
Landsat needs a full raster fetch, which is out of scope here; the scene metadata is
reported as availability evidence and never converted into invented index values.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from lib import ext_http

logger = logging.getLogger("agriguard.landsat")

STAC_URL = "https://landsatlook.usgs.gov/stac-server/search"
COLLECTION = "landsat-c2l2-sr"


async def search_scenes(bbox: List[float], days: int = 60, limit: int = 8) -> Dict[str, Any]:
    today = date.today()
    start = (today - timedelta(days=days)).isoformat()
    payload = {
        "collections": [COLLECTION],
        "bbox": [bbox[0], bbox[1], bbox[2], bbox[3]],
        "datetime": f"{start}T00:00:00Z/{today.isoformat()}T23:59:59Z",
        "limit": limit,
    }
    raw = await ext_http.request("POST", STAC_URL, source="landsat", json_body=payload)
    # USGS STAC replies with content-type application/geo+json, which ext_http returns as text.
    if isinstance(raw, (str, bytes)):
        import json as _json
        try:
            data = _json.loads(raw)
        except Exception as exc:
            raise RuntimeError(f"Landsat STAC returned unparseable payload: {exc}")
    else:
        data = raw
    feats = (data or {}).get("features") or []
    scenes: List[Dict[str, Any]] = []
    for f in feats:
        p = f.get("properties", {})
        scenes.append({
            "satellite": p.get("platform", "landsat"),
            "scene_id": f.get("id"),
            "product_id": p.get("landsat:product_id") or f.get("id"),
            "acquired": p.get("datetime"),
            "cloud_pct": p.get("eo:cloud_cover"),
            "wrs_path": p.get("landsat:wrs_path"),
            "wrs_row": p.get("landsat:wrs_row"),
            "collection": COLLECTION,
            "resolution": "30 m (optical), 15 m panchromatic",
            "source": "USGS Landsat Collection 2 Level-2 (STAC)",
        })
    scenes.sort(key=lambda s: s.get("acquired") or "", reverse=True)
    clear = [s for s in scenes if (s.get("cloud_pct") or 100) <= 30]
    return {
        "available": bool(scenes),
        "scene_count": (data or {}).get("numberMatched", len(scenes)),
        "scenes": scenes,
        "clear_scene_count": len(clear),
        "latest_acquired": scenes[0]["acquired"] if scenes else None,
        "latest_clear_acquired": clear[0]["acquired"] if clear else None,
        "window_days": days,
        "source": "USGS Landsat Collection 2 Level-2 (STAC, keyless)",
        "role": "Independent optical evidence and historical land condition context",
        "note": ("Scene metadata only — Landsat pixel indices require a raster fetch and are "
                 "reported as DATA UNAVAILABLE rather than estimated."),
    }
