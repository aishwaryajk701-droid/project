"""NASA Earth observation support — NASA POWER (keyless, real).

POWER serves MERRA-2 / GEOS satellite-assimilated daily rainfall, temperature and
humidity for any point. Used as an INDEPENDENT environmental cross-check against
Open-Meteo, never as a flood detector on its own.

Other NASA products that need an Earthdata token (GPM IMERG, SMAP soil moisture)
are exposed through the same interface but report DATA UNAVAILABLE until
NASA_API_KEY / Earthdata credentials are configured.
"""

import logging
import os
from datetime import date, timedelta
from statistics import mean
from typing import Any, Dict, List

from lib import ext_http

logger = logging.getLogger("agriguard.nasa")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def earthdata_configured() -> bool:
    return bool(os.environ.get("NASA_API_KEY") or os.environ.get("EARTHDATA_TOKEN"))


async def power_daily(lat: float, lng: float, days: int = 30) -> Dict[str, Any]:
    end = date.today() - timedelta(days=2)      # POWER lags ~2 days
    start = end - timedelta(days=days)
    params = {
        "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,RH2M",
        "community": "AG", "longitude": lng, "latitude": lat,
        "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    data = await ext_http.request("GET", POWER_URL, source="nasa", params=params)
    p = (((data or {}).get("properties") or {}).get("parameter") or {})
    rain = {k: v for k, v in (p.get("PRECTOTCORR") or {}).items() if v is not None and v > -900}
    temp = {k: v for k, v in (p.get("T2M") or {}).items() if v is not None and v > -900}
    rh = {k: v for k, v in (p.get("RH2M") or {}).items() if v is not None and v > -900}
    if not rain and not temp:
        raise RuntimeError("NASA POWER returned no usable values")
    days_sorted = sorted(rain.keys())
    last7 = [rain[d] for d in days_sorted[-7:]] if rain else []
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "rain_total_mm": round(sum(rain.values()), 1) if rain else None,
        "rain_last_7_days_mm": round(sum(last7), 1) if last7 else None,
        "rain_max_daily_mm": round(max(rain.values()), 1) if rain else None,
        "temp_mean_c": round(mean(temp.values()), 1) if temp else None,
        "temp_min_c": round(min((p.get("T2M_MIN") or {}).get(d, 99) for d in days_sorted), 1) if temp else None,
        "humidity_mean_pct": round(mean(rh.values()), 1) if rh else None,
        "daily_rain_mm": {d: rain[d] for d in days_sorted[-10:]} if rain else {},
        "source": "NASA POWER (MERRA-2 / GEOS satellite-assimilated reanalysis)",
        "resolution": "approximately 0.5 deg x 0.625 deg",
        "role": "Independent environmental cross-check for rainfall and temperature",
    }


def unavailable_products() -> List[Dict[str, str]]:
    """Products whose access needs Earthdata credentials — never faked."""
    if earthdata_configured():
        return []
    return [
        {"product": "GPM IMERG precipitation", "status": "NOT CONFIGURED",
         "detail": "Needs NASA Earthdata credentials (NASA_API_KEY / EARTHDATA_TOKEN)"},
        {"product": "SMAP soil moisture", "status": "NOT CONFIGURED",
         "detail": "Needs NASA Earthdata credentials (NASA_API_KEY / EARTHDATA_TOKEN)"},
        {"product": "OPERA DSWx surface water", "status": "NOT CONFIGURED",
         "detail": "Needs NASA Earthdata credentials (NASA_API_KEY / EARTHDATA_TOKEN)"},
    ]


def cross_check(nasa: Dict[str, Any] | None, open_meteo_rain7: float | None) -> Dict[str, Any]:
    """Agreement between two independent rainfall sources — evidence, not a verdict."""
    if not nasa or nasa.get("rain_last_7_days_mm") is None or open_meteo_rain7 is None:
        return {"status": "DATA UNAVAILABLE",
                "note": "Only one rainfall source available — no cross-check possible"}
    a, b = nasa["rain_last_7_days_mm"], float(open_meteo_rain7)
    diff = abs(a - b)
    tol = max(10.0, 0.4 * max(a, b))
    return {
        "status": "AGREE" if diff <= tol else "DISAGREE",
        "nasa_power_mm": a, "open_meteo_mm": b, "difference_mm": round(diff, 1),
        "note": (f"NASA POWER and Open-Meteo 7-day rainfall "
                 f"{'agree within' if diff <= tol else 'differ by more than'} "
                 f"{round(tol, 1)} mm — {'rainfall evidence is consistent' if diff <= tol else 'treat rainfall evidence with caution'}"),
    }
