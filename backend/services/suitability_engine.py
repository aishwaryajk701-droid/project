"""AgriGaurd Land Suitability engine — transparent weighted factors 0-100.

Factors: soil, moisture, terrain, flood condition, land cover, vegetation, weather.
Missing data lowers participation and is reported, never substituted.
"""

from typing import Any, Dict, Optional

DEFAULT_WEIGHTS: Dict[str, float] = {
    "soil": 25, "moisture": 15, "terrain": 15, "flood": 20, "landcover": 10, "vegetation": 10, "weather": 5,
}


def soil_factor(soil: Dict[str, Any] | None) -> Dict[str, Any] | None:
    from services.soil_service import texture_scores
    ts = texture_scores(soil)
    if not ts:
        return None
    vals = [v for v in ts.values() if v is not None]
    if not vals:
        return None
    return {"score": round(sum(vals) / len(vals), 1), "basis": "SoilGrids pH + organic carbon"}


def moisture_factor(ndmi: float | None, rain7: float | None) -> Dict[str, Any] | None:
    if ndmi is None and rain7 is None:
        return None
    parts, notes = [], []
    if ndmi is not None:
        parts.append(max(0.0, min(100.0, 55 + ndmi * 90)))
        notes.append(f"NDMI {ndmi}")
    if rain7 is not None:
        parts.append(max(20.0, min(95.0, 35 + rain7 * 1.2)))
        notes.append(f"7-day rain {rain7} mm")
    return {"score": round(sum(parts) / len(parts), 1), "basis": ", ".join(notes)}


def terrain_factor(terrain: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not terrain:
        return None
    return {"score": {"low": 90.0, "moderate": 72.0, "high": 50.0}.get(terrain.get("terrain_risk"), 72.0),
            "basis": f"Copernicus DEM — risk {terrain.get('terrain_risk')}"}


def flood_factor(flood_severity: str | None, ag_flood_pct: float | None) -> Dict[str, Any]:
    idx = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}.get(flood_severity or "none", 0)
    score = [92.0, 75.0, 48.0, 30.0, 15.0][idx]
    if ag_flood_pct is not None:
        score = max(10.0, score - ag_flood_pct * 0.4)
    return {"score": round(score, 1),
            "basis": f"flood severity '{flood_severity}' ({ag_flood_pct if ag_flood_pct is not None else 'n/a'}% ag. flood)"}


def vegetation_factor(ndvi: float | None) -> Dict[str, Any] | None:
    if ndvi is None:
        return None
    return {"score": round(max(15.0, min(95.0, 15 + ndvi * 100)), 1), "basis": f"NDVI {ndvi}"}


def weather_factor(recent: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not recent:
        return None
    last7 = recent.get("last_7_days_mm", 0) or 0
    # moderate rain is good; deluge lowers workability, drought lowers suitability
    if last7 >= 150:
        score, note = 45.0, "excessive rain"
    elif last7 >= 25:
        score, note = 88.0, "well-watered"
    elif last7 >= 5:
        score, note = 72.0, "some rain"
    else:
        score, note = 55.0, "dry week"
    return {"score": score, "basis": f"7-day rainfall {last7} mm ({note})"}


def compute_land_suitability(*, soil: Dict[str, Any] | None, terrain: Dict[str, Any] | None,
                             flood_severity: str | None, ag_flood_pct: float | None,
                             ndmi: float | None, rain7: float | None, ndvi: float | None,
                             landcover: Dict[str, Any] | None,
                             weather_recent: Dict[str, Any] | None = None,
                             weights: Dict[str, float] | None = None) -> Dict[str, Any]:
    from services.landcover_service import landcover_factor
    from services.weather_service import rainfall_verdict
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    factors: Dict[str, Dict[str, Any]] = {}
    f = soil_factor(soil);        factors["soil"] = f if f else {"score": None, "basis": "Soil data unavailable"}
    f = moisture_factor(ndmi, rain7); factors["moisture"] = f if f else {"score": None, "basis": "No NDVI/NDMI or rainfall"}
    f = terrain_factor(terrain);  factors["terrain"] = f if f else {"score": None, "basis": "DEM unavailable"}
    factors["flood"] = flood_factor(flood_severity, ag_flood_pct)
    f = landcover_factor(landcover); factors["landcover"] = f if f else {"score": None, "basis": "Land cover unavailable"}
    f = vegetation_factor(ndvi);  factors["vegetation"] = f if f else {"score": None, "basis": "Vegetation index unavailable"}
    recent = weather_recent if weather_recent else (
        {"last_7_days_mm": rain7} if rain7 is not None else None)
    rv = rainfall_verdict(recent or {}); f = weather_factor(recent)
    factors["weather"] = f if f else {"score": None, "basis": "Weather data unavailable"}

    used_w = {k: w[k] for k, v in factors.items() if v.get("score") is not None}
    score = (sum(factors[k]["score"] * v for k, v in used_w.items()) / sum(used_w.values())) if used_w else 50.0
    label = "High" if score >= 75 else "Moderate" if score >= 50 else "Low"
    return {
        "score": round(score, 1), "label": label, "weights": w,
        "factors": {k: {"score": v.get("score"), "basis": v.get("basis")} for k, v in factors.items()},
        "excluded_factors": [k for k, v in factors.items() if v.get("score") is None],
        "rainfall_statement": rv.get("statement"),
        "disclaimer": "Decision-support estimate from transparent weights — field verification recommended.",
    }
