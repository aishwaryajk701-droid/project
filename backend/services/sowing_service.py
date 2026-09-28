"""Sowing calendar engine.

For each recommended crop, turn the crop score + real rainfall (Open-Meteo archive
and forecast, as stored on the analysis) + current flood risk into a month-by-month
verdict: SOW NOW / PREPARE / WAIT / AVOID, each with the reason behind it.

Nothing is invented: when the analysis has no soil/weather/flood data, the affected
factor is reported as unavailable and the window is marked UNCERTAIN.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.crop_engine import CROPS, SEVERITY_FLOOD_INDEX, current_season

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Typical Indian sowing months per season (ICAR crop calendars).
SEASON_SOW_MONTHS = {
    "kharif": [6, 7],
    "rabi": [10, 11, 12],
    "zaid": [3, 4],
    "annual": [1, 2, 10, 11, 12],
}
SEASON_MONTHS = {
    "kharif": [6, 7, 8, 9, 10],
    "rabi": [10, 11, 12, 1, 2, 3],
    "zaid": [3, 4, 5],
    "annual": list(range(1, 13)),
}

# Drainage recovery time (days) before a flood-intolerant crop can be sown.
FLOOD_WAIT_DAYS = {"none": 0, "low": 7, "moderate": 14, "high": 28, "critical": 45}


def _crop_def(name: str) -> Optional[Dict[str, Any]]:
    return next((c for c in CROPS if c["name"] == name), None)


def _rain_context(analysis: Dict[str, Any]) -> Dict[str, Any]:
    wx = analysis.get("weather") or {}
    recent = wx.get("recent") or {}
    last7 = recent.get("last_7_days_mm")
    total30 = recent.get("total_mm")
    forecast = ((wx.get("current") or {}).get("daily_precip_sum_mm")
                if isinstance(wx.get("current"), dict) else None)
    return {"last_7_days_mm": last7, "last_30_days_mm": total30,
            "forecast_precip_mm": forecast,
            "available": last7 is not None or total30 is not None,
            "source": "Open-Meteo archive + forecast" if last7 is not None else None}


def _moisture_verdict(need: str, last7: Optional[float]) -> Dict[str, Any]:
    if last7 is None:
        return {"state": "unknown", "note": "Rainfall data unavailable — moisture not assessed"}
    if need in ("very_high", "high"):
        if last7 >= 40:
            return {"state": "good", "note": f"{last7} mm in the last 7 days supports a water-loving crop"}
        if last7 >= 15:
            return {"state": "marginal", "note": f"Only {last7} mm in 7 days — assured irrigation needed"}
        return {"state": "poor", "note": f"{last7} mm in 7 days is far below this crop's water need"}
    if need == "moderate":
        if 10 <= last7 <= 90:
            return {"state": "good", "note": f"{last7} mm in 7 days suits a moderate-water crop"}
        if last7 > 90:
            return {"state": "marginal", "note": f"{last7} mm in 7 days risks waterlogging at sowing"}
        return {"state": "marginal", "note": f"{last7} mm in 7 days — pre-sowing irrigation advised"}
    # low water need
    if last7 <= 40:
        return {"state": "good", "note": f"{last7} mm in 7 days suits a low-water crop"}
    return {"state": "poor", "note": f"{last7} mm in 7 days is too wet for a dryland crop"}


def _flood_verdict(crop: Dict[str, Any], severity: Optional[str],
                   ag_flood_pct: Optional[float], verified: bool = True) -> Dict[str, Any]:
    if severity is None:
        return {"state": "unknown", "wait_days": 0,
                "note": "Flood status unavailable — verify the field before sowing"}
    unverified = "" if verified else " (SAR flood detection unavailable — status unconfirmed)"
    idx = SEVERITY_FLOOD_INDEX.get(severity, 0)
    tol = crop["flood_tolerance"]
    wait = FLOOD_WAIT_DAYS.get(severity, 0)
    if tol >= 4:
        wait = max(0, wait - 14)
    if idx == 0:
        return {"state": "clear", "wait_days": 0,
                "note": f"No significant flood detected{unverified}"}
    pct = ag_flood_pct if ag_flood_pct is not None else 0
    if tol <= 1 and idx >= 2:
        return {"state": "blocking", "wait_days": wait,
                "note": (f"{severity} flood ({pct}% agricultural) and this crop tolerates flooding "
                         f"poorly — allow about {wait} days of drainage and verify the field")}
    return {"state": "caution", "wait_days": wait,
            "note": (f"{severity} flood ({pct}% agricultural); tolerance {tol}/5 — "
                     f"allow about {wait} days and check drainage")}


def _month_verdict(*, month: int, crop: Dict[str, Any], score: float,
                   moisture: Dict[str, Any], flood: Dict[str, Any],
                   this_month: int) -> Dict[str, Any]:
    sow_months: List[int] = []
    season_months: List[int] = []
    for s in crop["seasons"]:
        sow_months += SEASON_SOW_MONTHS.get(s, [])
        season_months += SEASON_MONTHS.get(s, [])
    in_sow = month in sow_months
    in_season = month in season_months

    if not in_season:
        return {"verdict": "AVOID", "reason": f"Outside the {', '.join(crop['seasons'])} window"}
    if not in_sow:
        return {"verdict": "PREPARE",
                "reason": "In season but past the usual sowing window — land preparation only"}
    if flood["state"] == "blocking" and month == this_month:
        return {"verdict": "WAIT", "reason": flood["note"]}
    if score < 50:
        return {"verdict": "AVOID",
                "reason": f"Crop score {score}/100 for this field's current soil and conditions"}
    if moisture["state"] == "poor" and month == this_month:
        return {"verdict": "WAIT", "reason": moisture["note"]}
    if flood["state"] == "unknown" or moisture["state"] == "unknown":
        return {"verdict": "UNCERTAIN",
                "reason": "Usual sowing month, but some source data is unavailable"}
    return {"verdict": "SOW NOW" if month == this_month else "SOW",
            "reason": f"Usual sowing month; crop score {score}/100, {moisture['note'].lower()}"}


def build_calendar(analysis: Dict[str, Any], field: Dict[str, Any] | None = None,
                   top: int = 4) -> Dict[str, Any]:
    """Build a per-crop month-by-month sowing calendar from one stored analysis."""
    now = datetime.now(timezone.utc)
    this_month = now.month
    flood_block = analysis.get("flood") or {}
    severity = flood_block.get("severity") or None
    sar_verified = bool(flood_block.get("available"))
    ag_pct = flood_block.get("agricultural_flood_pct")
    rain = _rain_context(analysis)
    recs = ((analysis.get("crops") or {}).get("recommendations") or [])[:top]

    crops_out: List[Dict[str, Any]] = []
    for rec in recs:
        cdef = _crop_def(rec.get("crop", ""))
        if not cdef:
            continue
        moisture = _moisture_verdict(cdef["moisture_need"], rain.get("last_7_days_mm"))
        flood = _flood_verdict(cdef, severity, ag_pct, sar_verified)
        months = [{"month": m, "label": MONTHS[m - 1],
                   **_month_verdict(month=m, crop=cdef, score=rec.get("score", 0),
                                    moisture=moisture, flood=flood, this_month=this_month)}
                  for m in range(1, 13)]
        best = [m["label"] for m in months if m["verdict"].startswith("SOW")]
        crops_out.append({
            "crop": cdef["name"],
            "score": rec.get("score"),
            "seasons": cdef["seasons"],
            "duration_days": cdef["duration_days"],
            "flood_tolerance": cdef["flood_tolerance"],
            "moisture_need": cdef["moisture_need"],
            "months": months,
            "sow_window": best,
            "current_verdict": next(m["verdict"] for m in months if m["month"] == this_month),
            "current_reason": next(m["reason"] for m in months if m["month"] == this_month),
            "drainage_wait_days": flood.get("wait_days", 0),
            "factors": {"moisture": moisture, "flood": flood,
                        "limits": cdef["limits"]},
        })

    return {
        "field_id": (field or {}).get("id") or analysis.get("field_id"),
        "field_name": (field or {}).get("name") or (analysis.get("boundary") or {}).get("name"),
        "analysis_id": analysis.get("id"),
        "analysis_date": analysis.get("created_at"),
        "month": this_month,
        "month_label": MONTHS[this_month - 1],
        "season": current_season(this_month),
        "rainfall": rain,
        "flood_severity": severity,
        "flood_verified": sar_verified,
        "agricultural_flood_pct": ag_pct,
        "crops": crops_out,
        "methodology": ("Sowing windows come from ICAR/FAO season calendars for each crop, then "
                        "adjusted by this field's crop score, the measured Open-Meteo rainfall and "
                        "the detected flood severity plus the crop's own flood tolerance. "
                        "Decision-support only — field verification recommended."),
        "limitations": [] if rain["available"] else ["Rainfall data unavailable — moisture factor not applied"],
    }
