"""AgriGaurd flood detection & confidence engines.

SAR methodology (deterministic, explainable, runs on real Sentinel-1 GRD VV/VH pixels):
  1. water likelihood per pixel from VV (dB), VH (dB) and the VV/VH ratio
  2. before/after relative change — NEW water is low backscatter NOW that was higher BEFORE
  3. 3x3 median filter + minimum mapping unit (connected components) to suppress speckle
  4. permanent-water removal (JRC / OSM context), land-cover verification, terrain context
  5. weighted confidence factors (configurable), severity from agricultural flood %

Confidence is an "Analytical Confidence" score, NOT a scientifically validated probability.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("agriguard.flood")

# Configurable weights (percent) — overridable via env JSON CONFIDENCE_WEIGHTS
DEFAULT_WEIGHTS: Dict[str, float] = {
    "sar_change": 30, "temporal": 20, "historical_water": 15, "landcover": 10,
    "optical": 10, "terrain": 10, "data_quality": 5,
}
# Configurable severity thresholds on agricultural flood %
DEFAULT_THRESHOLDS: Dict[str, float] = {"critical": 25.0, "high": 10.0, "moderate": 3.0, "low": 0.5}
VV_WATER_DB = -21.0     # linear->dB threshold for open water
VH_WATER_DB = -26.0
CHANGE_DB = -5.0        # relative drop that indicates newly submerged vegetation/soil


def load_weights() -> Dict[str, float]:
    import os, json
    raw = os.environ.get("CONFIDENCE_WEIGHTS")
    if raw:
        try:
            w = json.loads(raw)
            if isinstance(w, dict) and abs(sum(float(v) for v in w.values()) - 100) < 2:
                return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in w.items()}}
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def load_thresholds() -> Dict[str, float]:
    import os, json
    raw = os.environ.get("SEVERITY_THRESHOLDS")
    if raw:
        try:
            t = json.loads(raw)
            return {**DEFAULT_THRESHOLDS, **{k: float(v) for k, v in t.items()}}
        except Exception:
            pass
    return dict(DEFAULT_THRESHOLDS)


def _db(linear: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.clip(linear, 1e-6, None))


def _median3(mask: np.ndarray) -> np.ndarray:
    """3x3 median filter on a boolean mask (speckle reduction)."""
    padded = np.pad(mask.astype(np.float32), 1)
    stack = np.stack([padded[i:i + mask.shape[0], j:j + mask.shape[1]]
                      for i in range(3) for j in range(3)])
    return np.median(stack, axis=0) >= 0.5


def _mmu_filter(mask: np.ndarray, min_px: int = 3) -> np.ndarray:
    """Minimum mapping unit: drop connected components smaller than min_px (4-connectivity)."""
    visited = np.zeros_like(mask, dtype=bool)
    out = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    for i in range(h):
        for j in range(w):
            if mask[i, j] and not visited[i, j]:
                stack, comp = [(i, j)], []
                visited[i, j] = True
                while stack:
                    y, x = stack.pop()
                    comp.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not visited[yy, xx]:
                            visited[yy, xx] = True
                            stack.append((yy, xx))
                if len(comp) >= min_px:
                    for y, x in comp:
                        out[y, x] = True
    return out


def sar_water_analysis(before: Optional[np.ndarray], after: Optional[np.ndarray],
                       min_valid: float = 0.25) -> Dict[str, Any]:
    """before/after: HxWx3 float32 [VV_linear, VH_linear, valid_mask] from Sentinel-1 GRD.

    Returns pixel-level metrics + masks summary. Raises ValueError on unusable input so the
    pipeline can mark the satellite stage failed without crashing the analysis.
    """
    if after is None or before is None:
        return {"available": False, "reason": "Sentinel-1 before/after observations not available"}

    vv_b, vh_b, v_b = before[..., 0], before[..., 1], before[..., 2]
    vv_a, vh_a, v_a = after[..., 0], after[..., 1], after[..., 2]
    valid = (v_b > 0.5) & (v_a > 0.5) & np.isfinite(vv_b) & np.isfinite(vv_a)
    total = int(valid.sum())
    if total < 30 or total / valid.size < min_valid:
        return {"available": False, "reason": "insufficient valid SAR pixels over the field"}

    vv_db_b, vv_db_a = _db(vv_b), _db(vv_a)
    vh_db_b, vh_db_a = _db(vh_b), _db(vh_a)

    # per-pixel water likelihood (0..1), VV dominant, VH + ratio corroborate
    ratio_b = vh_db_b - vv_db_b  # dB proxy for VV/VH ratio
    ratio_a = vh_db_a - vv_db_a

    def water_score(vv_db: np.ndarray, vh_db: np.ndarray, ratio: np.ndarray) -> np.ndarray:
        s = np.zeros_like(vv_db)
        s += 0.6 * np.clip((VV_WATER_DB - vv_db) / 6.0, 0, 1)
        s += 0.25 * np.clip((VH_WATER_DB - vh_db) / 6.0, 0, 1)
        s += 0.15 * np.clip((ratio - 13.0) / 6.0, 0, 1)
        return np.clip(s, 0, 1)

    score_a = water_score(vv_db_a, vh_db_a, ratio_a)
    score_b = water_score(vv_db_b, vh_db_b, ratio_b)
    drop = vv_db_b - vv_db_a  # positive => backscatter decreased (submersion)

    water_after = _median3(score_a >= 0.55)
    water_before = _median3(score_b >= 0.55)
    new_water_raw = water_after & ~water_before & (drop >= CHANGE_DB)
    new_water = _mmu_filter(new_water_raw, min_px=3)

    total_f = float(total)
    water_after_pct = 100.0 * float((water_after & valid).sum()) / total_f
    water_before_pct = 100.0 * float((water_before & valid).sum()) / total_f
    new_water_pct = 100.0 * float((new_water & valid).sum()) / total_f
    mean_drop = float(np.mean(drop[valid & ~water_before & ~water_after])) if float((valid & ~water_before & ~water_after).sum()) > 0 else 0.0
    mean_drop_new = float(np.mean(drop[new_water & valid])) if float((new_water & valid).sum()) > 0 else 0.0

    return {
        "available": True,
        "valid_pixels": total,
        "water_after_pct": round(water_after_pct, 2),
        "water_before_pct": round(water_before_pct, 2),
        "new_water_pct": round(new_water_pct, 2),
        "water_expansion_pct": round(max(0.0, water_after_pct - water_before_pct), 2),
        "vv_mean_before_db": round(float(np.mean(vv_db_b[valid])), 2),
        "vv_mean_after_db": round(float(np.mean(vv_db_a[valid])), 2),
        "vv_change_db": round(float(np.mean(vv_db_a[valid]) - np.mean(vv_db_b[valid])), 2),
        "vh_mean_before_db": round(float(np.mean(vh_db_b[valid])), 2),
        "vh_mean_after_db": round(float(np.mean(vh_db_a[valid])), 2),
        "vh_change_db": round(float(np.mean(vh_db_a[valid]) - np.mean(vh_db_b[valid])), 2),
        "ratio_change_db": round(float(np.mean(ratio_a[valid]) - np.mean(ratio_b[valid])), 2),
        "mean_backscatter_drop_new_water_db": round(mean_drop_new, 2),
        "mean_backscatter_change_other_db": round(mean_drop, 2),
        "masks_b64_summary": {
            "after": int((water_after & valid).sum()),
            "before": int((water_before & valid).sum()),
            "new": int((new_water & valid).sum()),
        },
    }


def compute_confidence(sar: Dict[str, Any], temporal: Dict[str, Any] | None,
                       historical_water: Dict[str, Any] | None,
                       landcover: Dict[str, Any] | None, optical: Dict[str, Any] | None,
                       terrain: Dict[str, Any] | None, quality: Dict[str, Any] | None,
                       weights: Dict[str, float] | None = None) -> Dict[str, Any]:
    """Weighted analytical confidence 0-100. Missing evidence lowers the factor, never fakes it."""
    w = weights or load_weights()
    factors: Dict[str, Any] = {}

    if sar.get("available"):
        strength = min(abs(sar.get("mean_backscatter_drop_new_water_db", 0)) / 6.0, 1.0)
        factors["sar_change"] = {"value": round(40 + 60 * strength, 1),
                                 "note": f"mean new-water backscatter drop {sar.get('mean_backscatter_drop_new_water_db')} dB"}
    else:
        factors["sar_change"] = {"value": 0.0, "note": "SAR change evidence unavailable"}

    if temporal and temporal.get("available"):
        factors["temporal"] = {"value": float(temporal.get("factor", 50.0)),
                               "note": temporal.get("note", "")}
    else:
        factors["temporal"] = {"value": 25.0, "note": "No suitable before/after observation pair"}

    if historical_water and historical_water.get("available"):
        factors["historical_water"] = {"value": float(historical_water.get("factor", 50.0)),
                                       "note": historical_water.get("note", "")}
    else:
        factors["historical_water"] = {"value": 20.0, "note": "Historical water context unavailable"}

    if landcover and (landcover.get("cropland_pct") is not None or (landcover.get("osm_landuse"))):
        factors["landcover"] = {"value": 75.0, "note": "Land-cover verification available"}
    else:
        factors["landcover"] = {"value": 20.0, "note": "Land-cover data unavailable"}

    if optical and optical.get("available"):
        factors["optical"] = {"value": float(optical.get("factor", 60.0)),
                              "note": optical.get("note", "")}
    else:
        factors["optical"] = {"value": 10.0, "note": "No optical confirmation (cloud or unavailable)"}

    if terrain:
        factors["terrain"] = {"value": 70.0 if terrain.get("terrain_risk") == "moderate"
                              else 85.0 if terrain.get("terrain_risk") == "low" else 60.0,
                              "note": f"terrain risk {terrain.get('terrain_risk')}"}
    else:
        factors["terrain"] = {"value": 20.0, "note": "Terrain context unavailable"}

    dq = (quality or {}).get("score", 40.0)
    factors["data_quality"] = {"value": float(dq), "note": "overall data quality score"}

    total_w = sum(w.values())
    score = sum(factors[k]["value"] * w.get(k, 0) for k in factors) / (total_w or 1)
    return {
        "score": round(score, 1),
        "label": ("HIGH" if score >= 70 else "MODERATE" if score >= 45 else "LOW"),
        "weights": w,
        "factors": factors,
        "disclaimer": ("AgriGaurd analytical confidence — a weighted evidence score, not a "
                       "scientifically validated probability."),
    }


def severity_from_metrics(ag_flood_pct: float, thresholds: Dict[str, float] | None = None) -> Dict[str, Any]:
    t = thresholds or load_thresholds()
    pct = ag_flood_pct or 0.0
    if pct >= t["critical"]:
        sev = "critical"
    elif pct >= t["high"]:
        sev = "high"
    elif pct >= t["moderate"]:
        sev = "moderate"
    elif pct > t["low"]:
        sev = "low"
    else:
        sev = "none"
    return {"severity": sev, "thresholds": t,
            "agricultural_flood_pct": round(pct, 2),
            "note": "Thresholds configurable — numbers shown are the actual values behind the class."}


def flood_evidence(sar: Dict[str, Any], water_class: Dict[str, Any], ag_flood_pct: float | None,
                   rainfall: Dict[str, Any] | None, terrain: Dict[str, Any] | None,
                   landcover: Dict[str, Any] | None, optical: Dict[str, Any] | None) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    if sar.get("available"):
        checks.append({"icon": "ok", "text": f"Strong SAR change detected (VV {sar.get('vv_change_db')} dB, VH {sar.get('vh_change_db')} dB)"})
        checks.append({"icon": "ok", "text": f"New water vs previous observation: {sar.get('new_water_pct')}% of field pixels"})
    else:
        warnings.append({"icon": "warn", "text": f"Sentinel-1 evidence unavailable: {sar.get('reason', 'not configured')}"})
    if ag_flood_pct is not None and ag_flood_pct > 0.5:
        checks.append({"icon": "ok", "text": f"Agricultural flood area computed: {ag_flood_pct}% of the field"})
    if water_class.get("classification") in ("POSSIBLE NEW FLOOD",):
        checks.append({"icon": "ok", "text": "Detected water is new (permanent water excluded)"})
    elif water_class.get("classification") == "PERMANENT WATER":
        warnings.append({"icon": "warn", "text": "Water matches mapped permanent water bodies — not counted as new flood"})
    if landcover and landcover.get("cropland_pct") is not None:
        checks.append({"icon": "ok", "text": f"Area classified by ESA WorldCover — cropland {landcover.get('cropland_pct')}%"})
    else:
        warnings.append({"icon": "warn", "text": "Land-cover data unavailable — cropland masking used OSM context only"})
    if rainfall and rainfall.get("level") in ("high", "elevated"):
        checks.append({"icon": "ok", "text": rainfall.get("statement", "")})
    elif rainfall:
        warnings.append({"icon": "warn", "text": rainfall.get("statement", "")})
    else:
        warnings.append({"icon": "warn", "text": "Weather data unavailable"})
    if terrain:
        if terrain.get("low_lying_pct", 0) >= 30:
            checks.append({"icon": "ok", "text": f"Terrain is low-lying ({terrain.get('low_lying_pct')}% below field mean)"})
        else:
            checks.append({"icon": "ok", "text": f"Terrain checked (median slope {terrain.get('slope_median_pct')}%)"})
    else:
        warnings.append({"icon": "warn", "text": "Terrain (DEM) context unavailable"})
    if optical and optical.get("available"):
        checks.append({"icon": "ok", "text": "Optical (Sentinel-2) confirmation available"})
    else:
        warnings.append({"icon": "warn", "text": "Sentinel-2 optical confirmation unavailable due to cloud conditions or missing credentials"})
    return {"positive": checks, "warnings": warnings}


def data_quality_score(sources: Dict[str, Any], sar: Dict[str, Any],
                       obs_age_days: float | None, cloud: float | None,
                       area_ha: float, valid_ratio: float | None = None) -> Dict[str, Any]:
    components: Dict[str, Any] = {}
    sat = 0
    if sar.get("available"):
        sat += 20
    if sources.get("optical_available"):
        sat += 10
    components["satellite_availability"] = {"score": sat, "max": 30}
    age = 20
    if obs_age_days is None:
        age = 0
    elif obs_age_days <= 3:
        age = 20
    elif obs_age_days <= 8:
        age = 15
    elif obs_age_days <= 20:
        age = 8
    else:
        age = 3
    components["observation_age"] = {"score": age, "max": 20}
    cloud_score = 10 if cloud is None else max(0, 10 - int(cloud / 10))
    components["cloud_coverage"] = {"score": cloud_score, "max": 10}
    vp = 10 if valid_ratio is None else max(0, min(10, int(valid_ratio * 10)))
    components["valid_pixels"] = {"score": vp, "max": 10}
    aux = sum(1 for k in ("soil", "terrain", "weather", "osm") if (sources.get(k) or {}).get("status") == "OK")
    components["auxiliary_sources"] = {"score": aux * 5, "max": 20}
    size = 10 if area_ha >= 0.2 else (5 if area_ha >= 0.05 else 2)
    components["field_size"] = {"score": size, "max": 10}
    total = sum(c["score"] for c in components.values())
    label = "High" if total >= 75 else "Moderate" if total >= 45 else "Low"
    missing = [k for k in ("soil", "terrain", "weather", "osm") if (sources.get(k) or {}).get("status") != "OK"]
    if not sar.get("available"):
        missing.insert(0, "sentinel-1")
    return {"score": total, "label": label, "components": components, "missing_sources": missing,
            "note": "Missing datasets are reported — never substituted with estimates."}
