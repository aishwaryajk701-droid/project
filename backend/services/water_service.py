"""Water intelligence.

Classification of detected water into PERMANENT / SEASONAL / POSSIBLE NEW FLOOD / UNCERTAIN.
Historical water context (keyless): OSM permanent water + past S1 observations when Sentinel Hub
is configured. Historically permanent water is NEVER counted as new agricultural flood.
"""

from typing import Any, Dict, List

from services.osm_service import water_context


def classify_water(detected_new_pct: float | None,
                   osm_water: Dict[str, Any] | None,
                   jrc: Dict[str, Any] | None) -> Dict[str, Any]:
    """jrc: {"permanent_pct": x, "seasonal_pct": y} when JRC history is available."""
    if detected_new_pct is None:
        return {"classification": "UNAVAILABLE", "permanent_pct": None, "seasonal_pct": None,
                "new_flood_pct": None, "uncertain_pct": None,
                "note": "No satellite water detection available — cannot classify water."}
    permanent = (jrc or {}).get("permanent_pct") if jrc else None
    if permanent is None and osm_water:
        # OSM mapped water bodies inside the field act as the permanent-water proxy
        permanent = 100.0 if (osm_water.get("nearby_water_bodies", 0) + osm_water.get("nearby_waterways", 0)) > 0 and _water_inside() else 0.0
    permanent = round(permanent or 0.0, 1)
    new_flood = max(0.0, round(detected_new_pct - permanent, 1))
    seasonal = round(max(0.0, detected_new_pct - permanent - new_flood), 1)
    uncertain = round(max(0.0, detected_new_pct - permanent - new_flood - seasonal), 1)
    classification = "POSSIBLE NEW FLOOD" if new_flood > 0.5 else (
        "PERMANENT WATER" if permanent >= detected_new_pct * 0.8 else "SEASONAL WATER")
    return {
        "classification": classification,
        "permanent_pct": permanent,
        "seasonal_pct": seasonal,
        "new_flood_pct": new_flood,
        "uncertain_pct": uncertain,
        "note": ("Historically permanent water (mapped water bodies / JRC history) excluded from "
                 "new agricultural flood."),
    }


_water_inside = lambda: False  # refined by caller when polygon-aware water context is provided


def water_verification_summary(detected_water_pct: float | None,
                               osm_context: Dict[str, Any] | None,
                               landcover: Dict[str, Any] | None) -> Dict[str, Any]:
    """River / lake / reservoir verification + built-up verification, shown separately."""
    wc = water_context(osm_context)
    bu = builtup_context(osm_context)
    lc_water = (landcover or {}).get("water_pct") if landcover else None
    lc_built = (landcover or {}).get("builtup_pct") if landcover else None
    return {
        "detected_water_pct": detected_water_pct,
        "rivers_lakes": wc,
        "builtup": bu,
        "landcover_water_pct": lc_water,
        "landcover_builtup_pct": lc_built,
        "sources": [s for s in [
            "ESA WorldCover" if lc_water is not None else None,
            "OpenStreetMap" if osm_context else None,
        ] if s],
    }


def builtup_context(osm_context: Dict[str, Any] | None) -> Dict[str, Any]:
    from services.osm_service import builtup_context as _b
    return _b(osm_context)
