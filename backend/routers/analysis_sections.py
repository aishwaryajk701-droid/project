"""Per-analysis sub-resources: images, map layers, land, soil and crop sections.

Thin read-only projections of the stored analysis document so the frontend (and any
API client) can fetch one section at a time. Every response carries its provenance.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from lib.db import db
from lib.security import current_user

router = APIRouter(prefix="/analyses", tags=["analysis-sections"])


async def _owned(analysis_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db.analyses.find_one({"id": analysis_id, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")
    return doc


@router.get("/{analysis_id}/images")
async def analysis_images(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await _owned(analysis_id, user)
    imgs = doc.get("images") or {}
    disc = doc.get("discovery") or {}
    catalogue = [
        {"image_type": "s1_before", "satellite": "Sentinel-1 GRD",
         "date": (doc.get("before_window") or {}).get("to"), "resolution": "approximately 10 m",
         "source": "Copernicus / Sentinel Hub",
         "available": bool(imgs.get("s1_before_png_b64")),
         "png_b64": imgs.get("s1_before_png_b64")},
        {"image_type": "s1_after", "satellite": "Sentinel-1 GRD",
         "date": (doc.get("after_window") or {}).get("to"), "resolution": "approximately 10 m",
         "source": "Copernicus / Sentinel Hub",
         "available": bool(imgs.get("s1_after_png_b64")),
         "png_b64": imgs.get("s1_after_png_b64")},
    ]
    for t, sat in (("flood_mask", "Sentinel-1 derived"), ("flood_overlay", "Sentinel-1 derived"),
                   ("ndvi", "Sentinel-2 derived"), ("ndwi", "Sentinel-2 derived"),
                   ("landcover", "ESA WorldCover"), ("dem", "Copernicus DEM")):
        catalogue.append({"image_type": t, "satellite": sat, "date": None,
                          "resolution": None, "source": sat,
                          "available": bool(imgs.get(f"{t}_png_b64")),
                          "png_b64": imgs.get(f"{t}_png_b64")})
    missing = [c["image_type"] for c in catalogue if not c["available"]]
    return {
        "analysis_id": analysis_id, "field_id": doc.get("field_id"),
        "bbox": doc.get("bbox"), "images": catalogue, "missing": missing,
        "sentinel_hub_configured": bool(disc.get("sentinel_hub_configured")),
        "note": ("Raster products are rendered only when Sentinel Hub credentials are configured. "
                 "Missing images are reported as DATA UNAVAILABLE — never substituted with "
                 "placeholder or generated imagery."),
    }


@router.get("/{analysis_id}/layers")
async def analysis_layers(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await _owned(analysis_id, user)
    imgs = doc.get("images") or {}
    flood = doc.get("flood") or {}
    layers = [
        {"id": "boundary", "label": "Farm boundary", "kind": "vector", "available": True,
         "geometry": doc.get("boundary")},
        {"id": "s1_before", "label": "Sentinel-1 before", "kind": "raster",
         "available": bool(imgs.get("s1_before_png_b64"))},
        {"id": "s1_after", "label": "Sentinel-1 after", "kind": "raster",
         "available": bool(imgs.get("s1_after_png_b64"))},
        {"id": "flood_mask", "label": "Flood mask", "kind": "raster",
         "available": bool(imgs.get("flood_mask_png_b64")),
         "metric": flood.get("agricultural_flood_pct")},
        {"id": "ndvi", "label": "NDVI", "kind": "raster", "available": bool(doc.get("ndvi")),
         "metric": (doc.get("ndvi") or {}).get("mean")},
        {"id": "ndwi", "label": "NDWI", "kind": "raster", "available": bool(doc.get("ndwi")),
         "metric": (doc.get("ndwi") or {}).get("mean")},
        {"id": "landcover", "label": "Land cover", "kind": "raster",
         "available": (doc.get("landcover") or {}).get("composition") is not None},
        {"id": "dem", "label": "DEM / terrain", "kind": "raster", "available": bool(doc.get("terrain"))},
        {"id": "permanent_water", "label": "Permanent water", "kind": "raster",
         "available": bool((doc.get("water_verification") or {}).get("available"))},
    ]
    return {"analysis_id": analysis_id, "bbox": doc.get("bbox"), "layers": layers,
            "opacity_default": 0.7}


@router.get("/{analysis_id}/land")
async def analysis_land(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await _owned(analysis_id, user)
    lc = doc.get("landcover") or {}
    cropland = lc.get("cropland_pct")
    builtup = lc.get("builtup_pct")
    water = lc.get("water_pct")
    warning = None
    likely = "UNKNOWN"
    if cropland is not None:
        ranked = {"Agricultural": cropland, "Built-up": builtup or 0.0, "Water": water or 0.0}
        likely = max(ranked, key=lambda k: ranked[k])
        if cropland < 40:
            warning = ("Selected polygon may not represent agricultural land "
                       f"(cropland share {cropland}%). Crop suitability is shown for reference "
                       "only — verify the field on the ground.")
    else:
        osm = lc.get("osm_landuse") or {}
        if osm.get("total_landuse_polygons"):
            likely = ("Agricultural" if osm.get("agricultural_polygons", 0) > 0 else "Other")
            warning = ("Land-cover grid unavailable — classification falls back to OpenStreetMap "
                       "landuse polygons, which are coarser and incomplete.")
        else:
            warning = "Land cover DATA UNAVAILABLE — land type could not be verified."
    return {
        "analysis_id": analysis_id,
        "likely_land_type": likely,
        "composition": lc.get("composition"),
        "cropland_pct": cropland, "builtup_pct": builtup, "water_pct": water,
        "osm_landuse": lc.get("osm_landuse"),
        "vegetation": {"ndvi": doc.get("ndvi"), "ndwi": doc.get("ndwi"), "ndmi": doc.get("ndmi"),
                       "change": doc.get("vegetation_change")},
        "terrain": doc.get("terrain"), "terrain_status": doc.get("terrain_status"),
        "warning": warning,
        "source": lc.get("source") or "DATA UNAVAILABLE",
        "resolution": lc.get("resolution"),
    }


@router.get("/{analysis_id}/soil")
async def analysis_soil(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await _owned(analysis_id, user)
    soil = doc.get("soil")
    return {
        "analysis_id": analysis_id,
        "status": doc.get("soil_status", "DATA UNAVAILABLE"),
        "soil": soil,
        "weather": doc.get("weather"), "weather_status": doc.get("weather_status"),
        "nasa": doc.get("nasa"), "nasa_status": doc.get("nasa_status"),
        "nasa_cross_check": doc.get("nasa_cross_check"),
        "provenance": {
            "soil": "Dataset-derived (ISRIC SoilGrids)" if soil else "DATA UNAVAILABLE",
            "weather": "Dataset-derived (Open-Meteo)" if doc.get("weather") else "DATA UNAVAILABLE",
            "nasa": "Satellite-derived reanalysis (NASA POWER)" if doc.get("nasa") else "DATA UNAVAILABLE",
            "laboratory": "Not provided — satellite and dataset values are not a replacement for "
                          "laboratory soil testing",
        },
        "limitations": ["Satellite and gridded datasets are not a replacement for laboratory soil testing",
                        "Values are reported at the source resolution, never downscaled"],
    }


@router.get("/{analysis_id}/crop")
async def analysis_crop(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await _owned(analysis_id, user)
    land = await analysis_land(analysis_id, user)
    return {
        "analysis_id": analysis_id,
        "crops": doc.get("crops"),
        "land_suitability": doc.get("land_suitability"),
        "land_warning": land.get("warning"),
        "likely_land_type": land.get("likely_land_type"),
        "statement": ("AgriGaurd estimates crop suitability using satellite-derived farm "
                      "conditions combined with environmental and agricultural data. Satellite "
                      "imagery alone cannot determine exactly which crop to grow."),
    }


@router.get("/{analysis_id}/evidence")
async def analysis_evidence(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc = await _owned(analysis_id, user)
    return {
        "analysis_id": analysis_id,
        "multi_satellite": doc.get("multi_satellite"),
        "flood_evidence": (doc.get("flood") or {}).get("evidence"),
        "confidence": (doc.get("flood") or {}).get("confidence"),
        "data_quality": doc.get("data_quality"),
        "sources": doc.get("sources"),
        "limitations": doc.get("limitations"),
    }
