"""The AgriGaurd analysis pipeline orchestrator.

LOCATION → BOUNDARY → SATELLITE DISCOVERY → (SAR + OPTICAL + LAND COVER + WATER + DEM + SOIL
+ WEATHER + OSM CONTEXT) → FLOOD DETECTION → VERIFICATION → SUITABILITY → CROPS → EVIDENCE →
QUALITY → SAVE → ALERT.

Runs as an asyncio background job; stages update the job document so the frontend can poll
progress. Any single source failing downgrades the analysis to PARTIAL — the pipeline never
fabricates data and never crashes because one source is down.
"""

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib.db import db
from lib.geo import PolygonError, bbox_from_polygon, polygon_area_ha, polygon_centroid, validate_polygon
from lib.security import new_id
from services import crop_engine, flood_service, landcover_service, soil_service, terrain_service
from services import weather_service, osm_service, sentinel_service, water_service
from services import landsat_service, nasa_service, nisar_service, multisat_service
from services import demo_data, notification_service
from services.suitability_engine import compute_land_suitability

logger = logging.getLogger("agriguard.analysis")

STAGES = ["validating", "fetching_data", "processing_sar", "verifying_water", "analyzing_land",
          "processing_soil", "generating_recommendation", "saving_result"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _set_stage(job_id: str, stage: str, message: str, stage_status: str = "running") -> None:
    await db.analysis_jobs.update_one(
        {"job_id": job_id},
        {"$set": {f"stages.{stage}": {"status": stage_status, "message": message, "at": _now()},
                  "current_stage": stage, "updated_at": _now()}})


async def create_job(user: Dict[str, Any], coordinates: List[List[float]], *,
                     field: Dict[str, Any] | None = None, demo: bool = False,
                     name: str | None = None) -> Dict[str, Any]:
    job_id = new_id()
    doc = {
        "job_id": job_id, "user_id": user["id"],
        "field_id": (field or {}).get("id"),
        "demo": demo,
        "state": "QUEUED",
        "stages": {s: {"status": "pending", "message": "", "at": None} for s in STAGES},
        "current_stage": "validating",
        "created_at": _now(), "updated_at": _now(),
        "coordinates": coordinates, "name": name or (field or {}).get("name") or "Quick analysis",
    }
    await db.analysis_jobs.insert_one(doc.copy())
    return doc


async def run_job(job_id: str, coordinates: List[List[float]], user: Dict[str, Any],
                  field: Dict[str, Any] | None = None, demo: bool = False) -> None:
    """Execute the full pipeline. Guarantees a terminal state (COMPLETED / PARTIAL / FAILED)."""
    result: Dict[str, Any] = {}
    state = "FAILED"
    try:
        result, state = await _pipeline(job_id, coordinates, user, field, demo)
    except PolygonError as exc:
        await db.analysis_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"state": "FAILED", "error": str(exc), "updated_at": _now()}})
        await notification_service.audit(user.get("id"), "analysis_failed", {"error": str(exc)})
        return
    except Exception as exc:
        logger.exception("analysis job %s crashed", job_id)
        await db.analysis_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"state": "FAILED", "error": f"Unexpected error: {exc}", "updated_at": _now()}})
        await notification_service.audit(user.get("id"), "analysis_failed", {"error": str(exc)})
        return

    await db.analysis_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"state": state, "analysis_id": result.get("id"), "updated_at": _now(),
                  "result_summary": {
                      "flood_severity": (result.get("flood") or {}).get("severity"),
                      "agricultural_flood_pct": (result.get("flood") or {}).get("agricultural_flood_pct"),
                      "land_suitability": (result.get("land_suitability") or {}).get("score"),
                      "top_crop": ((result.get("crops") or {}).get("recommendations") or [{}])[0].get("crop"),
                  }}})
    await notification_service.audit(user.get("id"), "analysis_completed",
                                     {"analysis_id": result.get("id"), "state": state})


async def _pipeline(job_id: str, coordinates: List[List[float]], user: Dict[str, Any],
                    field: Dict[str, Any] | None, demo: bool) -> tuple[Dict[str, Any], str]:
    partial = False
    # ---------- 1. LOCATION / BOUNDARY ----------
    await _set_stage(job_id, "validating", "Validating field boundary")
    validate_polygon(coordinates)
    bbox = bbox_from_polygon(coordinates)
    area_ha = polygon_area_ha(coordinates)
    centroid = polygon_centroid(coordinates)
    await _set_stage(job_id, "validating", f"Boundary valid — {area_ha:.2f} ha", "done")

    # ---------- 2. SATELLITE DISCOVERY (optional Sentinel Hub) ----------
    await _set_stage(job_id, "fetching_data", "Discovering satellite observations and loading context data")
    sh_ok = sentinel_service.configured()
    discovery: Dict[str, Any] = {"sentinel_hub_configured": sh_ok, "demo_mode": demo}
    obs_age_days: Optional[float] = None
    cloud: Optional[float] = None
    sar_pair = None
    s2_pair = None
    before_window = after_window = None

    if sh_ok and not demo:
        from datetime import date, timedelta
        today = date.today()
        after_to = today
        after_from = after_to - timedelta(days=12)
        before_to = after_from - timedelta(days=2)
        before_from = before_to - timedelta(days=24)
        before_window = {"from": before_from.isoformat(), "to": before_to.isoformat()}
        after_window = {"from": after_from.isoformat(), "to": after_to.isoformat()}
        s1b, s1a = await asyncio.gather(
            sentinel_service.process_bands_tiff(bbox, before_from.isoformat(), before_to.isoformat(),
                                                "sentinel-1-grd", width=128),
            sentinel_service.process_bands_tiff(bbox, after_from.isoformat(), after_to.isoformat(),
                                                "sentinel-1-grd", width=128, mosaicking="mostRecent"))
        if s1a is not None and s1b is not None:
            sar_pair = {"before": s1b, "after": s1a}
        else:
            partial = True
        s2a = await sentinel_service.process_bands_tiff(bbox, after_from.isoformat(),
                                                        after_to.isoformat(), "sentinel-2-l2a",
                                                        width=128, mosaicking="leastCC",
                                                        max_cloud=40)
        if s2a is not None:
            s2_pair = {"after": s2a}
            cloud = 0.0  # leastCC selected ≤40%; exact cloud % comes from catalog metadata
        discovery["s1"] = {"available": sar_pair is not None}
        discovery["s2"] = {"available": s2_pair is not None}
        features = await sentinel_service.catalog_search(bbox, before_from.isoformat(),
                                                         after_to.isoformat(), "sentinel-1-grd")
        if features:
            dts = [f.get("properties", {}).get("datetime", "")[:10] for f in features[:10]]
            discovery["observations"] = [
                {"satellite": "Sentinel-1 GRD", "dates": dts,
                 "note": "latest available Sentinel-1 observations"}]
            try:
                if dts and dts[0]:
                    obs_age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(dts[0])).days
            except Exception:
                pass
    elif demo:
        pair = demo_data.demo_sar_pair()
        sar_pair = {"before": pair["before"], "after": pair["after"]}
        tc = demo_data.demo_true_color_pair()
        discovery["s1"] = {"available": True, "demo": True}
        discovery["observations"] = [
            {"satellite": "Sentinel-1 GRD (prepared sample)", "dates": ["DEMO-14", "DEMO-2"],
             "note": "prepared sample dataset"}]
        obs_age_days = 2.0
        before_window = {"from": "DEMO-14", "to": "DEMO-14"}
        after_window = {"from": "DEMO-2", "to": "DEMO-2"}
        sar_pair["before_png_b64"] = base64.b64encode(tc["before_png"]).decode()
        sar_pair["after_png_b64"] = base64.b64encode(tc["after_png"]).decode()
    else:
        partial = True
        discovery["s1"] = {"available": False,
                           "reason": "Sentinel Hub credentials not configured on this server"}
        discovery["s2"] = {"available": False,
                           "reason": "Sentinel Hub credentials not configured on this server"}
    await _set_stage(job_id, "fetching_data",
                     "Satellite discovery complete" if (sh_ok or demo) else
                     "No Sentinel Hub credentials — continuing with keyless sources", "done")

    # ---------- 3. KEYLESS CONTEXT (parallel; each failure isolated) ----------
    async def _weather():
        cw = await weather_service.current_weather(centroid[1], centroid[0])
        rr = await weather_service.recent_rainfall(centroid[1], centroid[0], 30)
        return {"current": cw.get("current"), "recent": rr,
                "verdict": weather_service.rainfall_verdict(rr),
                "source": "Open-Meteo", "resolution": "approximately 11 km grid"}

    async def _soil():
        return await soil_service.fetch_soil(centroid[1], centroid[0])

    async def _terrain():
        return await terrain_service.fetch_terrain(bbox)

    async def _osm():
        return await osm_service.fetch_osm_context(bbox)

    # ext_http.safe() guarantees a {"status": OK|DATA UNAVAILABLE} envelope per source, so a
    # single outage downgrades the analysis to PARTIAL instead of failing the whole job.
    from lib.ext_http import safe

    wx, sl, tn, oc, ls, ns = await asyncio.gather(
        safe("weather", _weather, "Open-Meteo"),
        safe("soil", _soil, "ISRIC SoilGrids"),
        safe("terrain", _terrain, "Copernicus DEM"),
        safe("osm", _osm, "OpenStreetMap Overpass"),
        safe("landsat", lambda: landsat_service.search_scenes(bbox), "USGS Landsat Collection 2"),
        safe("nasa", lambda: nasa_service.power_daily(centroid[1], centroid[0]), "NASA POWER"))

    if wx["status"] != "OK":
        partial = True
    if sl["status"] != "OK":
        partial = True
    if tn["status"] != "OK":
        partial = True
    if oc["status"] != "OK":
        partial = True

    # ---------- 4. SAR FLOOD DETECTION ----------
    await _set_stage(job_id, "processing_sar", "Processing Sentinel-1 SAR change detection")
    if sar_pair is not None:
        try:
            sar = flood_service.sar_water_analysis(sar_pair["before"], sar_pair["after"])
        except Exception as exc:
            logger.exception("SAR stage failed")
            sar = {"available": False, "reason": f"SAR processing failed: {exc}"}
            partial = True
    else:
        sar = {"available": False,
               "reason": "Sentinel Hub credentials not configured — add SENTINEL_HUB_CLIENT_ID/_SECRET to backend/.env"}
    await _set_stage(job_id, "processing_sar", "SAR change detection complete" if sar.get("available")
                     else "SAR unavailable — partial analysis", "done")

    # ---------- 5. WATER VERIFICATION ----------
    await _set_stage(job_id, "verifying_water", "Verifying permanent water, rivers and built-up areas")
    osm_ctx = oc.get("data")
    landcover = await landcover_service.fetch_land_cover(bbox, osm_ctx)
    if landcover.get("composition") is None:
        partial = True
    jrc = None  # JRC Global Surface Water requires Sentinel Hub / GEE — reported as NOT CONFIGURED
    water_class = water_service.classify_water(
        sar.get("new_water_pct") if sar.get("available") else None,
        water_service.water_verification_summary(sar.get("water_after_pct") if sar.get("available") else None,
                                                 osm_ctx, landcover)["rivers_lakes"],
        jrc)
    water_verif = water_service.water_verification_summary(
        sar.get("water_after_pct") if sar.get("available") else None, osm_ctx, landcover)
    await _set_stage(job_id, "verifying_water", "Water verification complete", "done")

    # ---------- 6. LAND COVER ----------
    await _set_stage(job_id, "analyzing_land", "Land cover composition", "done")

    # ---------- 7. SOIL / TERRAIN / WEATHER already fetched ----------
    await _set_stage(job_id, "processing_soil",
                     "SoilGrids + Copernicus DEM + Open-Meteo loaded", "done")

    # ---------- 8. VEGETATION (optical) ----------
    ndvi_stats = ndmi_stats = ndwi_stats = None
    veg_change = None
    if s2_pair is not None:
        try:
            import numpy as np
            arr = s2_pair["after"]
            b03, b04, b08, b11 = arr[..., 1], arr[..., 2], arr[..., 3], arr[..., 4]
            valid = (arr[..., 6] > 0.5) & np.isfinite(b08) & np.isfinite(b04)
            ndvi_arr = (b08 - b04) / (b08 + b04 + 1e-9)
            ndmi_arr = (b08 - b11) / (b08 + b11 + 1e-9)
            # NDWI (McFeeters 1996) = (Green - NIR) / (Green + NIR)
            ndwi_arr = (b03 - b08) / (b03 + b08 + 1e-9)
            if valid.sum() > 30:
                ndvi_stats = {"mean": float(np.nanmean(ndvi_arr[valid])),
                              "min": float(np.nanmin(ndvi_arr[valid])),
                              "max": float(np.nanmax(ndvi_arr[valid]))}
                ndmi_stats = {"mean": float(np.nanmean(ndmi_arr[valid])),
                              "min": float(np.nanmin(ndmi_arr[valid])),
                              "max": float(np.nanmax(ndmi_arr[valid]))}
                nd_mean = float(np.nanmean(ndwi_arr[valid]))
                ndwi_stats = {
                    "mean": nd_mean,
                    "min": float(np.nanmin(ndwi_arr[valid])),
                    "max": float(np.nanmax(ndwi_arr[valid])),
                    "water_pixel_pct": round(100.0 * float((ndwi_arr[valid] > 0).sum())
                                             / float(valid.sum()), 2),
                    "interpretation": ("open water / saturated surface" if nd_mean > 0.2
                                       else "moist surface" if nd_mean > 0
                                       else "no open-water signal"),
                    "formula": "NDWI = (B03 - B08) / (B03 + B08) — McFeeters 1996",
                    "role": "Supporting water/moisture evidence, not a standalone flood detector",
                }
        except Exception as exc:
            logger.warning("optical stats failed: %s", exc)
    if sar.get("available") and s2_pair is None:
        optical_note = "Sentinel-2 optical confirmation unavailable due to cloud conditions or missing credentials."
    elif s2_pair is not None:
        optical_note = "Optical confirmation available"
    else:
        optical_note = "Optical confirmation unavailable"
    optical = {"available": s2_pair is not None, "factor": 60 if s2_pair is not None else 10,
               "note": optical_note}

    # ---------- 9. FLOOD AGGREGATION ----------
    if sar.get("available"):
        total_water_pct = sar["water_after_pct"]
        new_water_pct = sar["new_water_pct"]
        # agricultural flood = new water that is NOT permanent water / built-up context
        permanent_pct = water_class.get("permanent_pct") or 0.0
        builtup_pct = (landcover.get("builtup_pct") or 0.0) if isinstance(landcover.get("builtup_pct"), (int, float)) else 0.0
        cropland_pct = landcover.get("cropland_pct")
        exclusion = min(1.0, (permanent_pct + builtup_pct + (100.0 - cropland_pct if cropland_pct is not None else 0.0)) / 100.0)
        ag_flood_pct = round(new_water_pct * (1 - exclusion), 2)
        total_water_ha = round(area_ha * total_water_pct / 100.0, 3)
        new_water_ha = round(area_ha * new_water_pct / 100.0, 3)
        ag_flood_ha = round(area_ha * ag_flood_pct / 100.0, 3)
    else:
        total_water_pct = new_water_pct = total_water_ha = new_water_ha = None
        ag_flood_pct = ag_flood_ha = None

    severity = flood_service.severity_from_metrics(ag_flood_pct if ag_flood_pct is not None else 0.0)

    # data quality
    sources = {"soil": sl, "terrain": tn, "weather": wx, "osm": oc,
               "optical_available": s2_pair is not None, "sar_available": sar.get("available")}
    quality = flood_service.data_quality_score(
        sources, sar, obs_age_days, cloud, area_ha,
        valid_ratio=(sar.get("valid_pixels", 0) / 16384.0) if sar.get("available") else None)

    confidence = flood_service.compute_confidence(
        sar, temporal={"available": sar.get("available", False), "factor": 70 if sar.get("available") else 25,
                       "note": "before/after comparison used"},
        historical_water={"available": bool((landcover.get("water_pct") or 0) > 0 or (osm_ctx and (osm_ctx.get("waterways") or osm_ctx.get("water_bodies")))),
                          "factor": 60 if water_class.get("classification") != "UNAVAILABLE" else 20,
                          "note": water_class.get("note", "")},
        landcover=landcover, optical=optical, terrain=tn.get("data"), quality=quality)
    if not sar.get("available"):
        partial = True

    evidence = flood_service.flood_evidence(sar, water_class, ag_flood_pct,
                                            wx.get("data", {}).get("verdict") if wx.get("data") else None,
                                            tn.get("data"), landcover, optical)
    if demo:
        demo_ev = demo_data.demo_evidence()
        evidence["positive"] = demo_ev["positive"]
        evidence["warnings"] = demo_ev["warnings"]

    flood_block = {
        "status": ("DETECTED" if (ag_flood_pct or 0) > severity["thresholds"]["low"] else
                   "NONE" if sar.get("available") else "UNAVAILABLE"),
        "total_water_pct": total_water_pct,
        "total_water_ha": total_water_ha,
        "new_water_pct": new_water_pct,
        "new_water_ha": new_water_ha,
        "agricultural_flood_pct": ag_flood_pct,
        "agricultural_flood_ha": ag_flood_ha,
        "flood_percentage": ag_flood_pct if ag_flood_pct is not None else 0.0,
        "affected_ha": ag_flood_ha if ag_flood_ha is not None else 0.0,
        "severity": severity["severity"], "severity_thresholds": severity["thresholds"],
        "confidence": confidence,
        "evidence": evidence,
        "sar": sar,
        "available": sar.get("available", False),
        "demo": demo,
    }

    # ---------- 10. SUITABILITY + CROPS ----------
    await _set_stage(job_id, "generating_recommendation", "Scoring land suitability and matching crops")
    recent = (wx.get("data") or {}).get("recent")
    rain7 = recent.get("last_7_days_mm") if recent else None
    suitability = compute_land_suitability(
        soil=sl.get("data"), terrain=tn.get("data"), flood_severity=severity["severity"],
        ag_flood_pct=ag_flood_pct, ndmi=(ndmi_stats or {}).get("mean"), rain7=rain7,
        ndvi=(ndvi_stats or {}).get("mean"), landcover=landcover, weather_recent=recent)
    crops = crop_engine.recommend_crops(
        soil=sl.get("data"), terrain=tn.get("data"), flood_severity=severity["severity"],
        ag_flood_pct=ag_flood_pct, ndmi=(ndmi_stats or {}).get("mean"), rain7=rain7,
        month=datetime.now(timezone.utc).month, state=(field or {}).get("state"),
        landcover_cropland_pct=landcover.get("cropland_pct"))
    await _set_stage(job_id, "generating_recommendation",
                     f"Suitability {suitability['score']}/100 — top crop: "
                     f"{crops['recommendations'][0]['crop'] if crops['recommendations'] else 'n/a'}", "done")

    # ---------- 11. SAVE ----------
    await _set_stage(job_id, "saving_result", "Saving analysis to database")
    # NDWI (McFeeters) comes from the Sentinel-2 block above; None when optical data is missing.
    nisar_block = await nisar_service.search_scenes(bbox)
    nasa_cross = nasa_service.cross_check(
        ns.get("data") if ns["status"] == "OK" else None,
        ((wx.get("data") or {}).get("recent") or {}).get("last_7_days_mm")
        if wx["status"] == "OK" else None)
    multi_sat = multisat_service.build_summary(
        sar=sar, discovery=discovery, ndvi=ndvi_stats, ndwi=ndwi_stats or ndmi_stats,
        landsat=ls.get("data") if ls["status"] == "OK" else None,
        nasa=ns.get("data") if ns["status"] == "OK" else None,
        nasa_cross_check=nasa_cross, nisar=nisar_block,
        terrain=tn.get("data") if tn["status"] == "OK" else None,
        landcover=landcover, water=water_verif,
        soil=sl.get("data") if sl["status"] == "OK" else None, osm=osm_ctx)
    record = {
        "id": new_id(), "user_id": user["id"],
        "field_id": (field or {}).get("id"), "type": "satellite",
        "demo": demo,
        "boundary": {"name": (field or {}).get("name") or "Quick analysis", "coordinates": coordinates},
        "bbox": bbox, "area_ha": round(area_ha, 3), "centroid": {"lat": centroid[1], "lng": centroid[0]},
        "state": (field or {}).get("state"), "district": (field or {}).get("district"),
        "village": (field or {}).get("village"),
        "before_window": before_window, "after_window": after_window,
        "discovery": discovery,
        "images": {
            "s1_before_png_b64": (sar_pair or {}).get("before_png_b64"),
            "s1_after_png_b64": (sar_pair or {}).get("after_png_b64"),
        },
        "flood": flood_block,
        "water_verification": water_verif,
        "water_classification": water_class,
        "landcover": landcover,
        "soil": sl.get("data") if sl["status"] == "OK" else None,
        "soil_status": sl["status"],
        "terrain": tn.get("data") if tn["status"] == "OK" else None,
        "terrain_status": tn["status"],
        "weather": wx.get("data") if wx["status"] == "OK" else None,
        "weather_status": wx["status"],
        "osm_context": osm_ctx,
        "ndvi": ndvi_stats, "ndmi": ndmi_stats, "ndwi": ndwi_stats,
        "vegetation_change": veg_change,
        "landsat": ls.get("data") if ls["status"] == "OK" else None,
        "landsat_status": ls["status"],
        "nasa": ns.get("data") if ns["status"] == "OK" else None,
        "nasa_status": ns["status"],
        "nasa_unavailable_products": nasa_service.unavailable_products(),
        "nasa_cross_check": nasa_cross,
        "nisar": nisar_block,
        "multi_satellite": multi_sat,
        "optical_note": optical_note,
        "land_suitability": suitability,
        "crops": crops,
        "data_quality": quality,
        "analysis_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "status": "PARTIAL" if partial else "ok",
        "message": ("Partial analysis — some sources unavailable; see data quality for details."
                    if partial else None),
        "sources": {
            "sentinel1": "Sentinel-1 GRD via Sentinel Hub" if sar.get("available") else "NOT CONFIGURED",
            "sentinel2": "Sentinel-2 L2A via Sentinel Hub" if s2_pair is not None else "NOT CONFIGURED",
            "landcover": landcover.get("source") or "DATA UNAVAILABLE",
            "water_history": "JRC Global Surface Water — NOT CONFIGURED (needs Sentinel Hub/GEE)",
            "soil": soil_service.RESOLUTION if sl["status"] == "OK" else "DATA UNAVAILABLE",
            "dem": terrain_service.DEM_RESOLUTION if tn["status"] == "OK" else "DATA UNAVAILABLE",
            "weather": "Open-Meteo" if wx["status"] == "OK" else "DATA UNAVAILABLE",
            "osm": "OpenStreetMap Overpass" if oc["status"] == "OK" else "DATA UNAVAILABLE",
            "landsat": (ls.get("data") or {}).get("source") if ls["status"] == "OK" else "DATA UNAVAILABLE",
            "nasa": (ns.get("data") or {}).get("source") if ns["status"] == "OK" else "DATA UNAVAILABLE",
            "nisar": nisar_block.get("status"),
        },
        "limitations": ["Remote-sensing based estimate", "Analytical confidence is not a validated probability",
                        "Field verification recommended"],
        "created_at": _now(),
    }
    await db.analyses.insert_one(record.copy())
    await _set_stage(job_id, "saving_result", "Analysis saved", "done")

    # ---------- 12. ALERTS ----------
    try:
        await notification_service.notify_flood(user, field, record)
    except Exception as exc:
        logger.warning("alert fan-out failed: %s", exc)

    # ---------- 13. UPDATE FIELD SNAPSHOT ----------
    if field:
        await db.fields.update_one(
            {"id": field["id"]},
            {"$set": {"last_analysis": record["analysis_date"],
                      "flood_status": flood_block["status"],
                      "flood_pct": ag_flood_pct or 0.0,
                      "flood_confidence": confidence["score"],
                      "land_suitability": suitability["score"],
                      "recommended_crop": (crops["recommendations"][0]["crop"]
                                           if crops["recommendations"] else None)}})
    return record, ("PARTIAL" if partial else "COMPLETED")
