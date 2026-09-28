"""Multi-satellite evidence summary.

Each source has ONE defined role — results are never blindly averaged. This module
collects what every source actually contributed to a finished analysis and produces a
transparent evidence table plus an agreement indicator.
"""

from typing import Any, Dict, List

ROLES = {
    "sentinel1": "Primary flood detector (C-band SAR change detection)",
    "sentinel2": "Optical water and vegetation evidence (NDVI / NDWI)",
    "landsat": "Independent optical evidence and historical land condition",
    "nasa": "Independent environmental cross-check (rainfall, temperature)",
    "nisar": "Additional L-band SAR flood evidence (optional)",
    "dem": "Terrain evidence (elevation, slope, low-lying share)",
    "landcover": "Agricultural-land evidence (cropland / built-up / water masks)",
    "jrc_water": "Permanent and seasonal water history",
    "soilgrids": "Soil property evidence",
    "osm": "Map context — rivers, water bodies, built-up areas",
}

DISCLAIMER = ("Confidence represents agreement and quality of available evidence; "
              "it is not a guarantee of classification accuracy.")


def _row(key: str, *, status: str, detail: str, source: str | None = None,
         acquired: str | None = None, resolution: str | None = None) -> Dict[str, Any]:
    return {"key": key, "role": ROLES.get(key, key), "status": status, "detail": detail,
            "source": source, "acquired": acquired, "resolution": resolution}


def build_summary(*, sar: Dict[str, Any] | None, discovery: Dict[str, Any] | None,
                  ndvi: Dict[str, Any] | None, ndwi: Dict[str, Any] | None,
                  landsat: Dict[str, Any] | None, nasa: Dict[str, Any] | None,
                  nasa_cross_check: Dict[str, Any] | None, nisar: Dict[str, Any] | None,
                  terrain: Dict[str, Any] | None, landcover: Dict[str, Any] | None,
                  water: Dict[str, Any] | None, soil: Dict[str, Any] | None,
                  osm: Dict[str, Any] | None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    s1_ok = bool((sar or {}).get("available"))
    rows.append(_row("sentinel1",
                     status="STRONG EVIDENCE" if s1_ok else "DATA UNAVAILABLE",
                     detail=((f"VV change {(sar or {}).get('vv_change_db')} dB, "
                              f"new water {(sar or {}).get('new_water_pct')}%")
                             if s1_ok else
                             ((sar or {}).get("reason")
                              or "Sentinel Hub credentials not configured — no SAR evidence used")),
                     source="Sentinel-1 GRD (Copernicus)",
                     acquired=(sar or {}).get("after_date"),
                     resolution="approximately 10 m"))

    s2_ok = bool(ndvi or ndwi)
    rows.append(_row("sentinel2",
                     status="SUPPORTING EVIDENCE" if s2_ok else "DATA UNAVAILABLE",
                     detail=((f"NDVI mean {(ndvi or {}).get('mean')}, "
                              f"NDWI mean {(ndwi or {}).get('mean')}")
                             if s2_ok else
                             "Optical confirmation unavailable (cloud cover or no credentials)"),
                     source="Sentinel-2 L2A (Copernicus)",
                     acquired=((discovery or {}).get("s2") or {}).get("acquired"),
                     resolution="approximately 10 m"))

    ls_ok = bool((landsat or {}).get("available"))
    rows.append(_row("landsat",
                     status="SUPPORTING EVIDENCE" if ls_ok else "DATA UNAVAILABLE",
                     detail=((f"{(landsat or {}).get('scene_count')} scenes in the last "
                              f"{(landsat or {}).get('window_days')} days, "
                              f"{(landsat or {}).get('clear_scene_count')} with cloud <= 30%")
                             if ls_ok else "No Landsat Collection-2 scenes returned for this AOI"),
                     source=(landsat or {}).get("source"),
                     acquired=(landsat or {}).get("latest_acquired"),
                     resolution="30 m"))

    nasa_ok = bool(nasa)
    rows.append(_row("nasa",
                     status="SUPPORTING EVIDENCE" if nasa_ok else "DATA UNAVAILABLE",
                     detail=((f"7-day rainfall {(nasa or {}).get('rain_last_7_days_mm')} mm, "
                              f"mean temp {(nasa or {}).get('temp_mean_c')} C; cross-check "
                              f"{(nasa_cross_check or {}).get('status')}")
                             if nasa_ok else "NASA POWER unavailable"),
                     source=(nasa or {}).get("source"),
                     acquired=((nasa or {}).get("period") or {}).get("end"),
                     resolution=(nasa or {}).get("resolution")))

    rows.append(_row("nisar",
                     status=(nisar or {}).get("status", "DATA UNAVAILABLE"),
                     detail=(nisar or {}).get("message", "NISAR data unavailable for this AOI/date"),
                     source=(nisar or {}).get("source"), resolution="L-band SAR"))

    t_ok = bool(terrain)
    rows.append(_row("dem",
                     status="SUPPORTING EVIDENCE" if t_ok else "DATA UNAVAILABLE",
                     detail=((f"Elevation {(terrain or {}).get('elevation_mean_m')} m, slope "
                              f"{(terrain or {}).get('slope_median_pct')}%, low-lying "
                              f"{(terrain or {}).get('low_lying_pct')}%")
                             if t_ok else "DEM unavailable"),
                     source=(terrain or {}).get("source"),
                     resolution=(terrain or {}).get("resolution")))

    lc_pct = (landcover or {}).get("cropland_pct")
    rows.append(_row("landcover",
                     status="SUPPORTING EVIDENCE" if lc_pct is not None else "DATA UNAVAILABLE",
                     detail=(f"Cropland {lc_pct}%, built-up {(landcover or {}).get('builtup_pct')}%"
                             if lc_pct is not None
                             else "Land-cover grid unavailable — OSM landuse used as a coarser proxy"),
                     source=(landcover or {}).get("source"),
                     resolution=(landcover or {}).get("resolution")))

    w_ok = bool((water or {}).get("available"))
    rows.append(_row("jrc_water",
                     status="SUPPORTING EVIDENCE" if w_ok else "DATA UNAVAILABLE",
                     detail=((f"Permanent water {(water or {}).get('permanent_water_pct')}%")
                             if w_ok else "Historical water occurrence unavailable"),
                     source=(water or {}).get("source")))

    s_ok = bool(soil)
    rows.append(_row("soilgrids",
                     status="SUPPORTING EVIDENCE" if s_ok else "DATA UNAVAILABLE",
                     detail=("Soil properties retrieved" if s_ok else "SoilGrids returned no usable layers"),
                     source=(soil or {}).get("source"),
                     resolution=(soil or {}).get("resolution")))

    o_ok = bool(osm)
    rows.append(_row("osm",
                     status="SUPPORTING EVIDENCE" if o_ok else "DATA UNAVAILABLE",
                     detail=("Waterways, water bodies and built-up features loaded" if o_ok
                             else "Overpass unavailable (public instance rate limit or timeout)"),
                     source="OpenStreetMap / Overpass"))

    available = [r for r in rows if r["status"] not in ("DATA UNAVAILABLE", "NOT CONFIGURED",
                                                        "NO COVERAGE")]
    agreement: Dict[str, Any] = {"status": "INSUFFICIENT EVIDENCE", "note": ""}
    flood_sources = [r for r in available if r["key"] in ("sentinel1", "sentinel2", "nisar")]
    if len(flood_sources) >= 2:
        agreement = {"status": "CORROBORATED",
                     "note": f"{len(flood_sources)} independent water-sensing sources contributed"}
    elif len(flood_sources) == 1:
        agreement = {"status": "SINGLE SOURCE",
                     "note": f"Only {flood_sources[0]['role'].lower()} contributed flood evidence"}
    else:
        agreement = {"status": "NO FLOOD SENSOR",
                     "note": ("No SAR or optical water evidence was available — flood metrics are "
                              "reported as DATA UNAVAILABLE, never estimated")}

    return {
        "sources": rows,
        "available_count": len(available),
        "total_count": len(rows),
        "agreement": agreement,
        "cross_checks": [c for c in [nasa_cross_check] if c],
        "disclaimer": DISCLAIMER,
        "separation_note": ("Flood detection uses SAR and optical water evidence only. Crop "
                            "suitability additionally combines soil, environment, location, season "
                            "and documented crop requirements."),
    }
