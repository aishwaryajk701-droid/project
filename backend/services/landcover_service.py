"""Land-cover intelligence.

Primary: ESA WorldCover 2021 grid sampling (keyless, real).
Fallback context: OSM landuse polygons (also real, coarser).
When both fail the land-cover section is DATA UNAVAILABLE — never estimated.
"""

from typing import Any, Dict, List

from lib import ext_http
from services import sentinel_service
from services.osm_service import cropland_context


async def fetch_land_cover(bbox: List[float], osm_context: Dict[str, Any] | None) -> Dict[str, Any]:
    sections: Dict[str, Any] = {"osm_landuse": cropland_context(osm_context)}

    try:
        wc = await sentinel_service.worldcover_grid(bbox)
        sections["worldcover"] = {"status": "OK", **wc}
        sections["composition"] = wc["percentages"]
        sections["cropland_pct"] = wc["percentages"].get("Cropland", 0.0)
        sections["builtup_pct"] = wc["percentages"].get("Built-up", 0.0)
        sections["water_pct"] = wc["percentages"].get("Permanent water", 0.0)
        sections["source"] = wc["source"]
        sections["resolution"] = wc["resolution"]
    except Exception as exc:
        sections["worldcover"] = {"status": "DATA UNAVAILABLE", "error": str(exc)[:200]}
        sections["composition"] = None
        sections["cropland_pct"] = None
        sections["builtup_pct"] = None
        sections["water_pct"] = None
        sections["source"] = None
        sections["resolution"] = None
    return sections


def landcover_factor(landcover: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not landcover:
        return None
    cropland = landcover.get("cropland_pct")
    if cropland is None:
        osm = landcover.get("osm_landuse") or {}
        if osm and osm.get("total_landuse_polygons"):
            share = osm["agricultural_polygons"] / max(osm["total_landuse_polygons"], 1)
            return {"score": max(40.0, min(90.0, 50.0 + share * 40.0)),
                    "basis": "OSM landuse polygons (coarser proxy)"}
        return None
    return {"score": max(40.0, min(95.0, 50.0 + cropland * 0.45)),
            "basis": "ESA WorldCover cropland share"}
